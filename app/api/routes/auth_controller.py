# app/api/routes/auth_controller.py
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user_model import Users
from app.schemas.auth_schema import LoginRequest, TokenResponse
from app.services.user_service import UserService
from app.services.activity_log_service import ActivityLogService

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    credenciales: LoginRequest,
    session: AsyncSession = Depends(get_db)
):
    # Capturamos la IP del cliente (equivalente a request.getRemoteAddr())
    ip_address = request.client.host if request.client else "unknown"

    # 1. Autenticación (incluye la comprobación de enabled=True que vimos antes)
    user = await UserService.authenticate_user(session, credenciales.username, credenciales.password)

    if not user:
        # Credenciales incorrectas o usuario inactivo — registramos el fallo
        await ActivityLogService.log(
            session=session,
            username=credenciales.username or "unknown",
            action="LOGIN_FAILED",
            detail=credenciales.username,
            ip=ip_address
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas"
        )

    # 2. Generar JWT
    # A diferencia de Java (JdbcTemplate), no necesitamos hacer una nueva consulta SQL
    # porque el objeto 'user' ya trae el atributo 'permiso' mapeado.
    #
    # INCORRECTO (lo que había antes): create_access_token(data={"sub": user.username, "rol": user.permiso})
    # Esa era la firma vieja de security.py (un dict libre), la que se eliminó en el
    # paso 5 justo para que este error no pudiera pasar. Con la firma actual
    # (username, role) ni "data=" ni "rol" existen: TypeError en cuanto se ejecuta.
    token = create_access_token(username=user.username, role=user.permiso)

    # 3. Registrar éxito
    await ActivityLogService.log(
        session=session,
        username=user.username,
        action="LOGIN_SUCCESS",
        detail=user.username,
        ip=ip_address
    )

    return TokenResponse(token=token)


@router.get("/protected")
async def protected_endpoint(current_user: Users = Depends(get_current_user)):
    # Antes: sin dependencia, respondía igual a cualquiera tuviera o no token.
    # get_current_user ya decodifica el JWT, busca al usuario en Aiven y
    # comprueba enabled=True; si algo falla, ni siquiera se llega a esta línea.
    return f"Hola {current_user.username}, estás autenticado con el rol {current_user.permiso}."