# tests/integration/conftest.py
#
# El nivel 3 de ESTRUCTURA §9: el @SpringBootTest + Testcontainers de Java.
# Lo que aqui se prueba es lo que solo un MySQL de verdad puede decir: las
# cascadas, los NOT NULL, la collation, el decimal. Contra la sesion falsa de
# tests/conftest.py todo eso pasa en verde aunque este roto.
#
# Este fichero HEREDA el de tests/ (pytest los encadena por carpetas) y
# sustituye una sola fixture: 'sesion'. Al llamarse igual, la de aqui tapa a
# la de arriba SOLO para los tests de esta carpeta -- los 195 siguen con su
# AsyncMock. Las demas (client, log, autenticar, limpiar_overrides) se heredan
# tal cual: 'log' sigue mockeado, porque el activity_log no es lo que se prueba.
import asyncio
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pymysql
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.community.mysql import MySqlContainer
from testcontainers.core.config import testcontainers_config

from app.core.database import get_db
from app.main import app

# Ryuk, apagado SOLO en Windows. Ryuk es un contenedor auxiliar que
# testcontainers arranca para borrar los demas si el proceso de Python muere
# de golpe. En Docker Desktop falla al arrancar, medido el 2026-10-13:
#     ConnectionError: Port mapping for container ... and port 8080 is not available
# DockerClient.port() pregunta UNA vez por el puerto, sin reintentar, justo
# despues de arrancar Ryuk, y Docker Desktop todavia no lo ha publicado. El
# reintento choca luego con el nombre del primer Ryuk (409 Conflict).
# MySQL no tiene el problema: a el se le pregunta despues de esperar a sus logs.
#
# Lo que se pierde: si se mata pytest a lo bruto (cerrar PyCharm a mitad de
# la bateria), el MySQL se queda vivo. Se ve y se borra con
#     docker ps --filter "ancestor=mysql:8.4"   /   docker rm -f <id>
# En un final normal, o con Ctrl+C, lo para el finally de la fixture 'mysql'.
# En la CI (Linux) Ryuk sigue encendido.
if sys.platform == "win32":
    testcontainers_config.ryuk_disabled = True

_AQUI = Path(__file__).parent
_ESQUEMA = _AQUI.parent / "schema.sql"
_BD = "easyfarma_dev"

# Aiven corre 8.0.45 y pasa a 8.4 despues del 31/10/2026 (BITACORA 10/10).
# Hasta entonces la bateria corre ENTERA en las dos: es la prueba de la subida
# que no se pudo hacer en una copia (el plan gratuito no permite fork).
# Despues del 31/10: quitar la 8.0 y fijar la 8.4 con el SELECT VERSION() que
# de Aiven -- "mysql:8.4" a secas es el ultimo parche, no el de produccion.
_IMAGENES = ["mysql:8.0.45", "mysql:8.4"]

# Las seis tablas. Solo se usa para vaciarlas entre test y test.
_TABLAS = ["ventas", "authorities", "ventas_canceladas", "activity_log", "articulos", "users"]


# -------------------------------------------------------------------------
# 0. Marcar como 'integration' todo lo que hay en esta carpeta
# -------------------------------------------------------------------------
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Pone @pytest.mark.integration a cada test de tests/integration.

    Asi no depende de acordarse de escribir 'pytestmark' en cada fichero
    nuevo: uno que se olvidara correria con el 'pytest' a secas y tumbaria
    la CI, que no tiene Docker.

    tryfirst=True no es decorativo: el filtro de -m "not integration" (el
    addopts de pytest.ini) se aplica en ESTE MISMO hook, dentro del plugin de
    marcas de pytest. Si el marcador se pusiera despues, el filtro ya habria
    pasado y no deseleccionaria nada.
    """
    for item in items:
        if _AQUI in Path(item.fspath).parents:
            item.add_marker(pytest.mark.integration)


# -------------------------------------------------------------------------
# 1. El bucle de eventos: el mismo que en produccion
# -------------------------------------------------------------------------
def pytest_asyncio_loop_factories(config, item):
    """SelectorEventLoop en Windows, para los tests de esta carpeta.

    Medido: pytest-asyncio en Windows crea un ProactorEventLoop. Es el bucle
    con el que aiomysql + TLS revienta contra Aiven (OperationalError 2003 /
    WinError 87), y por eso el CMD del Dockerfile lleva
    --loop asyncio:SelectorEventLoop. Aqui no hay TLS, pero si los tests
    corren en otro bucle que la app, prueban otra cosa.

    Se hace con este hook y NO sobrescribiendo la fixture event_loop_policy:
    eso pytest-asyncio 1.4 ya lo marca como deprecated, y
    WindowsSelectorEventLoopPolicy desaparece en Python 3.16. En Linux (la
    CI) devuelve None: alli el bucle por defecto ya es el Selector.
    """
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return None


# -------------------------------------------------------------------------
# 2. El contenedor: uno por version de MySQL, para toda la sesion
# -------------------------------------------------------------------------
@pytest.fixture(scope="session", params=_IMAGENES)
def mysql(request) -> Iterator[MySqlContainer]:
    """Arranca un MySQL en Docker y le carga tests/schema.sql.

    Ambito de SESION: arrancar MySQL cuesta ~12 s, una vez por version y no
    una por test. Es sincrona a proposito -- testcontainers habla con Docker
    sin async --, asi que no choca con asyncio_default_fixture_loop_scope =
    function del pytest.ini.

    Con params=, pytest agrupa los tests: primero todos contra 8.0.45, para el
    contenedor, luego todos contra 8.4. La imagen sale en el nombre del test.

    Tres trampas, las tres comprobadas:
      * NO pasar dialect="aiomysql" al constructor para que
        get_connection_url() de ya la URL async: el propio arranque del
        contenedor la usaria con un create_engine() SINCRONO, y aiomysql es
        solo async -> MissingGreenlet. La URL async se monta a mano en la
        fixture 'engine'.
      * NO usar seed= para cargar el esquema: testcontainers copia esos
        ficheros DESPUES de arrancar el contenedor (MySqlContainer.start hace
        super().start() y luego _transfer_seed()), en carrera con el
        entrypoint de MySQL, que puede haber pasado ya por esa carpeta.
        Se carga a mano, una vez listo.
      * El import es testcontainers.community.mysql; testcontainers.mysql
        sigue existiendo pero avisa de que esta deprecated.
    """
    contenedor = MySqlContainer(request.param, dbname=_BD)
    contenedor.start()
    try:
        _cargar_esquema(contenedor)
        yield contenedor
    finally:
        contenedor.stop()


def _cargar_esquema(contenedor: MySqlContainer) -> None:
    """Ejecuta tests/schema.sql sentencia a sentencia, con PyMySQL sincrono.

    PyMySQL ya estaba instalado (aiomysql esta construido encima), y en una
    fixture sincrona evita montar un bucle de eventos solo para el DDL.

    El fichero se trocea por ';' tras quitar los comentarios '--': ninguna
    sentencia del esquema lleva ';' dentro de una cadena, y si un dia la
    llevara, el CREATE fallaria aqui con un error de sintaxis, no en silencio.
    """
    sin_comentarios = "\n".join(
        linea for linea in _ESQUEMA.read_text(encoding="utf-8").splitlines()
        if not linea.lstrip().startswith("--")
    )
    sentencias = [s.strip() for s in sin_comentarios.split(";") if s.strip()]

    conexion = pymysql.connect(
        host=contenedor.get_container_host_ip(),
        port=int(contenedor.get_exposed_port(3306)),
        user=contenedor.username,
        password=contenedor.password,
        database=_BD,
        charset="utf8mb4",
    )
    try:
        with conexion.cursor() as cursor:
            for sentencia in sentencias:
                cursor.execute(sentencia)
        conexion.commit()
    finally:
        conexion.close()


# -------------------------------------------------------------------------
# 3. El engine: uno por test, contra el contenedor
# -------------------------------------------------------------------------
@pytest.fixture
async def engine(mysql: MySqlContainer) -> AsyncIterator[AsyncEngine]:
    """El engine de la app, pero apuntando al contenedor. Vacia las tablas.

    Por test y no por sesion: un engine async queda atado al bucle de
    eventos en el que abre sus conexiones, y aqui cada test tiene el suyo
    (pytest.ini). NullPool para que no sobreviva ninguna conexion de un test
    al siguiente.

    Se VACIA antes de cada test en vez de envolverlo en una transaccion con
    rollback: los services hacen commit() de verdad, y hay comportamientos
    (el DEFAULT CURRENT_TIMESTAMP, el bloqueo optimista con dos sesiones) que
    solo se ven con datos confirmados. TRUNCATE ademas reinicia los
    AUTO_INCREMENT, asi que los id son predecibles. FOREIGN_KEY_CHECKS=0 es
    por conexion: tiene que ir en la misma que los TRUNCATE.

    El dispose() del final es el que pedia ESTRUCTURA §9: sin el, aiomysql
    suelta "RuntimeError: Event loop is closed" desde el __del__ de la
    conexion cuando el bucle del test ya se cerro.
    """
    url = (
        f"mysql+aiomysql://{mysql.username}:{mysql.password}"
        f"@{mysql.get_container_host_ip()}:{mysql.get_exposed_port(3306)}/{_BD}"
        "?charset=utf8mb4"
    )
    motor = create_async_engine(url, poolclass=NullPool)
    async with motor.begin() as conexion:
        await conexion.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for tabla in _TABLAS:
            await conexion.execute(text(f"TRUNCATE TABLE `{tabla}`"))
        await conexion.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    try:
        yield motor
    finally:
        await motor.dispose()


# -------------------------------------------------------------------------
# 4. La sesion: la REAL, tapando a la falsa de tests/conftest.py
# -------------------------------------------------------------------------
@pytest.fixture(autouse=True)
async def sesion(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sustituye a la 'sesion' de tests/conftest.py en esta carpeta.

    Dos cosas distintas, como en produccion:
      * La sesion que recibe el TEST, para preparar datos y comprobar como
        quedo la base despues.
      * get_db, sustituido por un generador que abre una sesion NUEVA por
        peticion, como el get_db real. Si la peticion usara la misma sesion
        que el test, el test veria los objetos en memoria y no lo que de
        verdad se escribio en MySQL.

    Mismas opciones que AsyncSessionLocal (core/database.py):
    autoflush=False y expire_on_commit=False. Con otras, los tests probarian
    una sesion que no es la de la app.
    """
    fabrica = async_sessionmaker(
        bind=engine, class_=AsyncSession, autoflush=False, expire_on_commit=False
    )

    async def _get_db_contenedor() -> AsyncIterator[AsyncSession]:
        async with fabrica() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db_contenedor
    async with fabrica() as s:
        yield s
