# app/api/deps.py
# OBSOLETO: from typing import AsyncGenerator
# Sólo lo usaba la firma del get_db duplicado que se ha quitado de aquí (y en
# core/database.py se importa de collections.abc, no de typing: el de typing
# está deprecado desde Python 3.9).
import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
import jwt



# Importaciones de tu proyecto
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user_model import Users
from app.repositories.user_repository import UserRepository

# ANTES: oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
#
# Pintaba en el botón "Authorize" de Swagger el formulario del flujo OAuth2:
# usuario, contraseña, client_id y client_secret. Dos problemas:
#
#   1. NO FUNCIONABA. Ese formulario envía las credenciales como formulario
#      (username=...&password=...&grant_type=password) y /auth/login espera
#      JSON, porque es lo que le manda el Angular. Medido contra el
#      contenedor: form -> 422, JSON -> 401/200. El candado estaba pintado y
#      no había manera de conseguir el token por ahí.
#   2. client_id y client_secret identifican a la APLICACIÓN en un OAuth2 de
#      verdad (una app de terceros pidiendo acceso a tu cuenta). Esta API no
#      los usa ni los mirará nunca: dos campos que sólo confunden.
#
# HTTPBearer pinta una sola caja donde se pega el token, que es exactamente
# lo que hace el Swagger del backend Java. El flujo pasa a ser: llamas a
# /auth/login desde el propio /docs, copias el "token" de la respuesta, lo
# pegas en Authorize, y a partir de ahí Swagger manda
# "Authorization: Bearer <token>" en todas las peticiones.
#
# Esto NO cambia nada para el Angular: el esquema de seguridad sólo vive en
# el openapi.json, que únicamente lee Swagger.
#
# auto_error=False y el 401 se lanza aquí abajo a mano, por dos razones:
# para que el cuerpo del error sea el mismo tanto si falta la cabecera como
# si el token es malo, y porque el código que devuelve HTTPBearer por su
# cuenta ha cambiado con las versiones de FastAPI (era 403, hoy en la 0.141.1
# es 401). Con auto_error=False no depende de eso.
bearer_scheme = HTTPBearer(auto_error=False)


# -------------------------------------------------------------------
# 1. DEPENDENCIA DE BASE DE DATOS (El EntityManager)
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# 2. DEPENDENCIA DE SEGURIDAD (El filtro de Spring Security)
# -------------------------------------------------------------------
async def get_current_user(
        # ANTES: token: str = Depends(oauth2_scheme)   -> llegaba el token pelado.
        # HTTPBearer devuelve un objeto con .scheme ("Bearer") y .credentials
        # (el token), o None si no vino la cabecera (auto_error=False).
        credenciales: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        # Inyectamos la sesión de BD para poder buscar al usuario
        session: AsyncSession = Depends(get_db)
) -> Users:
    """Valida el JWT y devuelve la entidad User completa"""

    excepcion_credenciales = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Sin cabecera Authorization, o con una que no empieza por "Bearer ".
    if credenciales is None:
        raise excepcion_credenciales

    token = credenciales.credentials

    try:
        # 1. Decodificar el JWT (Equivalente a tu JwtUtil.validateToken en Java)
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        # ExpiredSignatureError hereda de InvalidTokenError, así que la cubre
        # también (token caducado, firma inválida, manipulado, alg=none, claims
        # obligatorios ausentes: decode_access_token exige exp y sub).
        raise excepcion_credenciales

    username: str = payload["sub"]

    # 2. Buscar al usuario en la base de datos usando el Repositorio que ya armaste
    user = await UserRepository.find_by_username(session, username=username)
    if user is None:
        raise excepcion_credenciales

    # AÑADIDO EN EL PASO 12 — suelta la conexión del pool antes de seguir.
    #
    # Sin esta línea, el SELECT de arriba deja una de las 3 conexiones de Aiven
    # (pool_size=3, max_overflow=0) retenida hasta que TERMINA la petición, no
    # hasta que acaba la consulta. Da igual en un endpoint que sólo toca la BD,
    # pero /api/cima/** habla con AEMPS (hasta 10 s) y con la IA (hasta 30):
    # tres búsquedas lentas a la vez dejaban sin conexiones al resto de la API,
    # y la cuarta petición esperaba el pool_timeout (30 s) para morir con 500.
    #
    # El Java no tenía este problema aquí: autentica con JdbcUserDetailsManager,
    # que devuelve la conexión al momento (misma cuota, hikari.maximum-pool-size=3).
    #
    # INCORRECTO (lo que propuso el revisor): await session.rollback()
    # También suelta la conexión, pero CADUCA los atributos de 'user' (medido:
    # expired_attributes = ['id', 'name'] tras rollback, [] tras commit, aunque
    # AsyncSessionLocal vaya con expire_on_commit=False). Luego, el primer
    # current_user.username del endpoint intentaría recargar la fila y en async
    # eso revienta con MissingGreenlet.
    #
    # Aquí commit() no "guarda" nada: no hay nada pendiente, esta dependencia
    # corre antes del cuerpo del endpoint. Sólo cierra la transacción de lectura.
    await session.commit()

    # 3. Validar reglas de negocio (ej. si fue baneado después de emitir el token)
    if not getattr(user, 'enabled', True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )

    # Devolvemos el objeto User. Quien llame a esta dependencia tendrá al usuario listo.
    return user


# -------------------------------------------------------------------
# 3. DEPENDENCIA DE ROLES (@PreAuthorize / hasRole del Java)
# -------------------------------------------------------------------
def require_role(*roles: str):
    """Fábrica de dependencias: Depends(require_role("SUPERADMIN")).

    Equivale a @PreAuthorize("hasRole('SUPERADMIN')"). No hay decorador de ese
    tipo en FastAPI, así que la forma idiomática es una dependencia que se
    declara por ruta — de ahí que esto sea una función que DEVUELVE una
    dependencia, no una dependencia en sí misma.

    'roles' se compara contra Users.permiso tal cual viene de la BD
    ("SUPERADMIN", no "ROLE_SUPERADMIN"): es el mismo valor crudo que ya
    lleva el JWT (ver §6 bis de ESTRUCTURA.md), así que no hace falta tocar
    prefijos aquí.
    """

    async def role_checker(current_user: Users = Depends(get_current_user)) -> Users:
        if current_user.permiso not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para acceder a este recurso",
            )
        return current_user

    return role_checker


# -------------------------------------------------------------------
# 4. DEPENDENCIA DEL CLIENTE HTTP (el @Autowired RestTemplate)
# -------------------------------------------------------------------
def get_http_client(request: Request) -> httpx.AsyncClient:
    """Devuelve el httpx.AsyncClient único que crea el lifespan de main.py.

    No crea nada: sólo lo saca de app.state. Así cima_service.py e
    ia_service.py lo reciben como parámetro (igual que la AsyncSession) y en
    los tests se sustituye con dependency_overrides sin tocar los services.
    """
    return request.app.state.http_client