# app/api/deps.py
# OBSOLETO: from typing import AsyncGenerator
# Sólo lo usaba la firma del get_db duplicado que se ha quitado de aquí (y en
# core/database.py se importa de collections.abc, no de typing: el de typing
# está deprecado desde Python 3.9).
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
import jwt  # PyJWT, no python-jose

# INCORRECTO (lo que había antes):
#     from jose import JWTError, jwt
#     from app.core.config import settings  # Donde guardas tu SECRET_KEY
#
# Tres fallos a la vez, y ninguno lo pilla el editor porque los tres son
# nombres que "podrían" existir:
#   1. 'jose' no es la librería de este proyecto: no está en requirements.txt
#      (aquí se eligió PyJWT, ya usada en core/security.py). Con solo
#      requirements.txt instalado, esto es ModuleNotFoundError.
#   2. config.py no expone ninguna variable 'settings': solo get_settings()
#      con @lru_cache, a propósito (paso 2), para que los tests puedan
#      sustituirla. ImportError inmediato, comprobado ejecutando el fichero.
#   3. Aunque 'settings' existiera, el campo se llama jwt_secret, no
#      SECRET_KEY.

# Importaciones de tu proyecto
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user_model import Users
from app.repositories.user_repository import UserRepository

# Esto le dice a FastAPI y a Swagger dónde está el endpoint de login
# Actúa como el puente automático para que el botón "Authorize" de Swagger funcione
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# -------------------------------------------------------------------
# 1. DEPENDENCIA DE BASE DE DATOS (El EntityManager)
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# 2. DEPENDENCIA DE SEGURIDAD (El filtro de Spring Security)
# -------------------------------------------------------------------
async def get_current_user(
        # FastAPI inyecta aquí el token extraído del header 'Authorization: Bearer <token>'
        token: str = Depends(oauth2_scheme),
        # Inyectamos la sesión de BD para poder buscar al usuario
        session: AsyncSession = Depends(get_db)
) -> Users:
    """Valida el JWT y devuelve la entidad User completa"""

    excepcion_credenciales = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
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