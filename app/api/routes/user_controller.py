# app/api/routes/user_controller.py
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

# INCORRECTO (lo que había antes):
#     # Suponemos una dependencia que extrae el payload del JWT {"sub": "ko2", "rol": "ADMIN"}
#     from app.api.dependencies.auth_deps import get_current_token_payload
#
# Dos fallos, y el segundo es mucho peor que el primero:
#
# 1. El módulo no existe: es la CUARTA vez en el proyecto y la misma ruta
#    inventada que en el paso 9. Es app/api/deps.py (sin subcarpeta) y la
#    dependencia es get_current_user, que devuelve la entidad Users entera,
#    igual que el UserDetails de Spring — no un payload.
#
# 2. "Suponemos" + .get("rol"): el claim se llama "role", no "rol" (§6 bis;
#    es exactamente el error que ya se coló en auth_controller.py en el paso
#    6). Sobre el payload real, .get("rol", "") devuelve "" para TODO EL
#    MUNDO, así que rol_caller nunca vale "ADMIN" y las tres reglas de abajo
#    no se disparan JAMÁS: ni el 403 ni el FORBIDDEN_ACTION. Un fallo que se
#    abre en vez de cerrarse, y sin ruido. Comprobado:
#        claims reales del token: ['exp', 'iat', 'role', 'sub']
#        p.get("rol", "") -> ''
#
# Con get_current_user no hay payload que interpretar: el rol sale de
# current_user.permiso, leído de la BD en ESTA petición. Es más estricto que
# el SecurityContextHolder del Java, que lo saca del token: si a alguien le
# bajan el rol, su token viejo sigue diciendo ADMIN hasta que caduque.
from app.api.deps import get_current_user
from app.models.user_model import Users
from app.schemas.user_schema import UserCreate, UserUpdate, UserOut
from app.services.user_service import UserService
from app.services.activity_log_service import ActivityLogService
# DuplicateResourceException ya no hace falta aquí: el chequeo del duplicado
# vive en UserService.crear_usuario (ver el comentario de POST /insert).
from app.exceptions.custom import ResourceNotFoundException

# TU VERSIÓN: APIRouter(prefix="/users", tags=["Users"])
#
# Sin dependencies=[...] quedaban abiertos sin token GET /users/all y
# GET /users/{username}; los otros tres pedían get_current_user como
# parámetro y por eso sí exigían JWT. Es el MISMO agujero del paso 9 en
# /articulos, y por el mismo motivo: en el Java no se declara endpoint por
# endpoint porque SecurityConfig acaba en .anyRequest().authenticated().
# Medido antes de arreglarlo, sin cabecera Authorization:
#     GET /users/all        -> 200  [devolvió 9 usuarios SIN token]
#     GET /users/testuser   -> 200
#     POST /insert, PUT /update, DELETE /{id} -> 401
#
# VERSIÓN INTERMEDIA (correcta, pero movida el 2026-10-04):
#     router = APIRouter(
#         prefix="/users",
#         tags=["Users"],
#         dependencies=[Depends(get_current_user)],
#     )
#
# El gate sigue existiendo, pero ahora vive en el include_router() de
# router.py, junto al del resto de prefijos, como en SecurityConfig.java. Lo
# que NO se puede mover allí son las reglas finas de abajo (ADMIN sólo crea
# SELLER, ADMIN no toca a ADMIN/SUPERADMIN, SELLER no escribe): dependen del
# rol del usuario OBJETIVO, no del que llama, y además registran un
# FORBIDDEN_ACTION antes del 403, así que son lógica de este controlador.
router = APIRouter(prefix="/users", tags=["Users"])


# ENDURECIMIENTO DELIBERADO respecto al Java (2026-10-01).
#
# En el Java, un SELLER con un token válido puede llamar a /users/insert y
# crearse un SUPERADMIN: UserController sólo mira "ADMIN".equals(rolCaller), y
# en TODO el backend hay UN único control de rol (SecurityConfig:64,
# /activity-log/** -> SUPERADMIN; ni un @PreAuthorize en el proyecto). La
# restricción del SELLER existe sólo en el Angular: home.component.html:57
# esconde "Gestión Usuarios" con *ngIf="userRole!='SELLER'". Esconder el botón
# no es proteger el endpoint: basta un curl con el token de un vendedor.
#
# Aquí se cierra en el servidor, en los TRES endpoints que escriben. Los dos GET
# se quedan como en el Java (autenticado a secas). No rompe al frontend: a un
# SELLER no le ofrece nunca esa pantalla.
#
# No se usa require_role("ADMIN", "SUPERADMIN") de deps.py, que sería lo
# idiomático, porque esto además deja rastro: un SELLER tocando /users es justo
# lo que interesa ver en el activity_log.
async def _denegar(session: AsyncSession, username_caller: str, detalle: str,
                   ip: str, mensaje: str) -> NoReturn:
    """Registra el FORBIDDEN_ACTION y corta con un 403. Nunca devuelve.

    NoReturn es el aviso al editor (y a mypy) de que después de esta llamada no
    hay camino de vuelta: no tiene sentido comprobar nada detrás.
    """
    await ActivityLogService.log(session, username_caller, "FORBIDDEN_ACTION", detalle, ip)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=mensaje)


@router.get("/all", response_model=list[UserOut])
async def obtener_todos(session: AsyncSession = Depends(get_db)):
    usuarios = await UserService.get_all_users(session)
    if not usuarios:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return usuarios


# /users/{username} DEBE ir después de /users/all para que FastAPI no confunda "all" con un username
@router.get("/{username}", response_model=UserOut)
async def obtener_por_username(username: str, session: AsyncSession = Depends(get_db)):
    usuario = await UserService.get_user_by_username(session, username)
    if not usuario:
        raise ResourceNotFoundException(f"Usuario no encontrado: {username}")
    return usuario


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_usuario(
        id: int,
        request: Request,
        session: AsyncSession = Depends(get_db),
        # TU VERSIÓN: token_payload: dict = Depends(get_current_token_payload)
        current_user: Users = Depends(get_current_user)
):
    # TU VERSIÓN (ver el import: "rol" no es un claim del token, era siempre ""):
    #     rol_caller = token_payload.get("rol", "")
    #     username_caller = token_payload.get("sub", "unknown")
    rol_caller = current_user.permiso
    username_caller = current_user.username
    ip_address = request.client.host if request.client else "unknown"

    # ENDURECIMIENTO (ver _denegar): el Java deja pasar al SELLER por aquí.
    if rol_caller == "SELLER":
        await _denegar(session, username_caller,
                       "Intento de DELETE de usuario siendo SELLER", ip_address,
                       "Un SELLER no puede gestionar usuarios")

    usuario_objetivo = await UserService.get_user_by_id(session, id)
    if not usuario_objetivo:
        raise ResourceNotFoundException(f"Usuario no encontrado con id: {id}")

    permiso_objetivo = usuario_objetivo.permiso
    username_objetivo = usuario_objetivo.username

    # Restricción: ADMIN no puede eliminar usuarios de igual o mayor jerarquía
    if rol_caller == "ADMIN" and permiso_objetivo in ["ADMIN", "SUPERADMIN"]:
        await ActivityLogService.log(
            session, username_caller, "FORBIDDEN_ACTION",
            f"Intento de DELETE sobre usuario {username_objetivo} con rol {permiso_objetivo}", ip_address
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un ADMIN no puede eliminar usuarios con rol ADMIN o SUPERADMIN"
        )

    await UserService.delete_user_by_id(session, id)
    await ActivityLogService.log(session, username_caller, "DELETE_USER", username_objetivo, ip_address)

    return None


@router.post("/insert", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def insertar_usuario(
        insert_dto: UserCreate,
        request: Request,
        session: AsyncSession = Depends(get_db),
        # TU VERSIÓN: token_payload: dict = Depends(get_current_token_payload)
        current_user: Users = Depends(get_current_user)
):
    # TU VERSIÓN (ver el import: "rol" no es un claim del token, era siempre ""):
    #     rol_caller = token_payload.get("rol", "")
    #     username_caller = token_payload.get("sub", "unknown")
    rol_caller = current_user.permiso
    username_caller = current_user.username
    ip_address = request.client.host if request.client else "unknown"

    # ENDURECIMIENTO (ver _denegar): el Java deja pasar al SELLER por aquí.
    if rol_caller == "SELLER":
        await _denegar(session, username_caller,
                       "Intento de crear usuario siendo SELLER", ip_address,
                       "Un SELLER no puede gestionar usuarios")

    # Restricción: ADMIN solo puede crear usuarios con rol SELLER
    if rol_caller == "ADMIN" and insert_dto.permiso != "SELLER":
        await ActivityLogService.log(
            session, username_caller, "FORBIDDEN_ACTION",
            f"Intento de crear usuario con rol {insert_dto.permiso}", ip_address
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un ADMIN solo puede crear usuarios con rol SELLER"
        )

    # TU VERSIÓN (fiel al Java, que lo comprueba aquí en UserController:115):
    #     usuario_existente = await UserService.get_user_by_username(session, insert_dto.username)
    #     if usuario_existente:
    #         # Usamos tu excepción personalizada que el handler convertirá en 409
    #         raise DuplicateResourceException("El usuario ya existe")
    #
    # Quitado porque hoy está DOS veces: en el paso 9 bis (a) se añadió el mismo
    # chequeo dentro de UserService.crear_usuario, que es donde no se puede
    # saltar — da igual quién llame al service. Dejarlo aquí eran dos SELECT
    # por cada alta para la misma pregunta. Sigue saliendo 409, lo lanza el
    # service y lo traduce handlers.py.

    nuevo_usuario = await UserService.crear_usuario(
        session, insert_dto.username, insert_dto.password, insert_dto.permiso
    )

    await ActivityLogService.log(session, username_caller, "INSERT_USER", nuevo_usuario.username, ip_address)
    return nuevo_usuario


@router.put("/update", response_model=UserOut)
async def actualizar_usuario(
        usuario_update: UserUpdate,
        request: Request,
        session: AsyncSession = Depends(get_db),
        # TU VERSIÓN: token_payload: dict = Depends(get_current_token_payload)
        current_user: Users = Depends(get_current_user)
):
    # TU VERSIÓN (ver el import: "rol" no es un claim del token, era siempre ""):
    #     rol_caller = token_payload.get("rol", "")
    #     username_caller = token_payload.get("sub", "unknown")
    rol_caller = current_user.permiso
    username_caller = current_user.username
    ip_address = request.client.host if request.client else "unknown"

    # ENDURECIMIENTO (ver _denegar): el Java deja pasar al SELLER por aquí.
    if rol_caller == "SELLER":
        await _denegar(session, username_caller,
                       "Intento de modificar usuario siendo SELLER", ip_address,
                       "Un SELLER no puede gestionar usuarios")

    usuario_objetivo = await UserService.get_user_by_id(session, usuario_update.id)
    if not usuario_objetivo:
        raise ResourceNotFoundException(f"Usuario no encontrado con ID: {usuario_update.id}")

    permiso_objetivo = usuario_objetivo.permiso
    username_objetivo = usuario_objetivo.username

    # Restricción: ADMIN no puede modificar usuarios de igual o mayor jerarquía
    if rol_caller == "ADMIN" and permiso_objetivo in ["ADMIN", "SUPERADMIN"]:
        await ActivityLogService.log(
            session, username_caller, "FORBIDDEN_ACTION",
            f"Intento de modificar usuario {username_objetivo} con rol {permiso_objetivo}", ip_address
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un ADMIN no puede modificar usuarios con rol ADMIN o SUPERADMIN"
        )

    # Actualizamos pasando el ID, el nuevo permiso y opcionalmente la nueva contraseña
    usuario_actualizado = await UserService.actualizar_usuario(
        session,
        user_id=usuario_update.id,
        permiso=usuario_update.permiso,
        raw_password=usuario_update.password
    )

    return usuario_actualizado