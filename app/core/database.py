# app/core/database.py
#
# Reúne tres cosas que en Spring venían de tres sitios distintos:
#   engine             -> el DataSource de Hikari (el pool de conexiones)
#   AsyncSessionLocal  -> el EntityManagerFactory / SessionFactory de Hibernate
#   get_db()           -> el EntityManager que Spring inyecta en cada petición

import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import get_settings

# INCORRECTO (lo que había antes):
#     engine = create_async_engine(Settings.database_url, ...)
#
# database_url es una @property. Accedida sobre la CLASE devuelve el objeto
# property; la cadena sólo aparece si se accede sobre una INSTANCIA. SQLAlchemy
# lo dijo con todas las letras al importar el módulo:
#
#     sqlalchemy.exc.ArgumentError: Expected string or URL object,
#                                   got <property object at 0x0000022781B17E70>
#
# Es el mismo error que en Java llamar a un método de instancia como si fuera
# static: el compilador te para, aquí no para nadie hasta que se ejecuta.
settings = get_settings()

# ── TLS contra Aiven ──────────────────────────────────────────────────────
#
# INCORRECTO (esto lo dicté mal yo, no es tuyo):
#     ssl_context = ssl.create_default_context()
#
# Dije que Aiven usaba una CA pública y que el contexto por defecto bastaba.
# No es cierto: Aiven firma el certificado del servidor con una CA propia, así
# que la verificación falla con
#
#     ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
#     certificate verify failed: self-signed certificate in certificate chain
#
# La solución NO es desactivar la verificación (eso es lo que hace el backend
# Java con verifyServerCertificate=false: cifra, pero no comprueba con quién
# habla, así que no protege de un man-in-the-middle). Se le pasa el ca.pem de
# la consola de Aiven, que está en la raíz del repositorio, y así queda
# verify_mode=CERT_REQUIRED y check_hostname=True. Es el truststore de Java.
#
# El fichero no es un secreto: es el certificado público de la CA. Por eso va
# versionado, y por eso su ruta vive en Settings y no escrita a mano aquí.
ssl_context = ssl.create_default_context(cafile=str(settings.aiven_ca_file))

# ── El pool de conexiones ─────────────────────────────────────────────────
#
# create_async_engine no abre nada todavía: configura el pool. La primera
# conexión real se abre con la primera consulta (SQLAlchemy es perezoso, y por
# eso muchos errores de aquí no saltan al arrancar sino en la primera query).
engine = create_async_engine(
    settings.database_url,
    pool_size=3,          # Limita las conexiones a la BD, como hikari.maximum-pool-size=3
    max_overflow=0,       # No permite abrir conexiones extra por encima del pool_size
    pool_pre_ping=True,   # Comprueba que la conexión está viva antes de usarla (test-on-borrow)
    # AÑADIDO: Aiven cierra las conexiones que llevan un rato ociosas. Con sólo
    # pool_pre_ping te enteras al usarla (y gastas un ping); reciclándolas cada
    # 30 minutos no llegas a tener conexiones zombis en el pool. Es el
    # maxLifetime de Hikari.
    pool_recycle=1800,
    connect_args={"ssl": ssl_context},  # Inyecta el SSL obligatorio para Aiven
    # TU VERSIÓN: echo=False fijo.
    # Funciona, pero así lo tienes atado al entorno y en producción no se
    # llenan los logs de SQL. Es el spring.jpa.show-sql del application.properties.
    echo=settings.environment == "dev",
)

# ── La factoría de sesiones ───────────────────────────────────────────────
#
# async_sessionmaker equivale a tu EntityManagerFactory / Session de Hibernate.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # autocommit=False es un parámetro legacy que SQLAlchemy 2.0 todavía acepta,
    # pero SÓLO con el valor False (su firma es autocommit: Literal[False]).
    # No hace nada: se deja porque documenta la intención y no molesta.
    autocommit=False,
    autoflush=False,
    # Sin esto, tras un commit SQLAlchemy marca los atributos como caducados y
    # el siguiente venta.id dispararía una consulta nueva... desde código
    # síncrono, lo que revienta con MissingGreenlet. Es el equivalente a que la
    # entidad se te quede detached al salir del @Transactional.
    expire_on_commit=False,
)


# ── La dependencia que se inyecta en cada endpoint ────────────────────────
#
# Un generador asíncrono: lo de antes del yield es el @Before, lo de después el
# finally. Se usará como Depends(get_db) — el @PersistenceContext de Spring.
#
# Aquí NO se hace commit a propósito: la transacción la abre el servicio con
# "async with session.begin()", igual que el @Transactional está en el
# @Service y no en el @RestController.
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # TU VERSIÓN (no estaba mal, sólo era redundante):
    #     async with AsyncSessionLocal() as session:
    #         try:
    #             yield session
    #         finally:
    #             await session.close()
    #
    # El "async with" ya llama a session.close() al salir del bloque, pase lo
    # que pase y también si el endpoint lanza una excepción. El try/finally
    # cerraba una sesión que ya estaba cerrada.
    async with AsyncSessionLocal() as session:
        yield session
