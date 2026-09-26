# app/services/user_service.py
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_model import Users
from app.models.authority_model import Authorities
from app.repositories.user_repository import UserRepository

from app.core.security import verify_password, get_password_hash


class UserService:

    @staticmethod
    async def get_all_users(session: AsyncSession) -> Sequence[Users]:
        return await UserRepository.find_all(session)

    @staticmethod
    async def get_user_by_id(session: AsyncSession, user_id: int) -> Users | None:
        return await UserRepository.find_by_id(session, user_id)

    @staticmethod
    async def get_user_by_username(session: AsyncSession, username: str) -> Users | None:
        return await UserRepository.find_by_username(session, username)

    @staticmethod
    async def delete_user_by_id(session: AsyncSession, user_id: int) -> None:
        """Borrado logico: pone enabled=False, no hace un DELETE fisico.

        DESVIACION DELIBERADA respecto al Java: UserController.java borra la
        fila de verdad. Aqui no puede: "users" tiene dos FK con
        ON DELETE CASCADE (authorities.username y ventas.id_username,
        comprobado en information_schema contra Aiven), asi que un DELETE
        real se llevaria por delante TODO el historial de ventas del usuario
        sin avisar. Con enabled=False el usuario deja de poder autenticarse
        (ver el chequeo en authenticate_user) y ventas + activity_log de su
        username se quedan intactos. La fila de authorities NO se toca: el
        backend Java comparte la misma tabla y su propio login tambien debe
        respetar enabled=False.
        """
        # LO VIEJO (borraba la fila de verdad, arrastraba las ventas por el cascade):
        #     await UserRepository.delete(session, user)
        #     await session.commit()
        user = await UserRepository.find_by_id(session, user_id)
        if not user:
            # En FastAPI, las excepciones personalizadas luego se capturan para devolver 404
            raise ValueError(f"Usuario no encontrado con id: {user_id}")

        user.enabled = False
        await session.commit()

    @staticmethod
    async def crear_usuario(session: AsyncSession, username: str, raw_password: str, permiso: str) -> Users:
        # 1. Encriptar contraseña de forma asíncrona (reemplaza a passwordEncoder)
        hashed_password = await get_password_hash(raw_password)

        # 2. Instanciar el usuario
        nuevo_usuario = Users(
            username=username,
            password=hashed_password,
            enabled=True,
            permiso=permiso
        )
        await UserRepository.save(session, nuevo_usuario)

        # 3. Guardar el rol en authorities para la compatibilidad con Spring Security
        nueva_autoridad = Authorities(username=username, role=f"ROLE_{permiso}")
        session.add(nueva_autoridad)

        # 4. Confirmar la transacción para ambas tablas
        await session.commit()

        return nuevo_usuario

    @staticmethod
    async def actualizar_usuario(session: AsyncSession, user_id: int, permiso: str,
                                 raw_password: str | None = None) -> Users:
        # 1. Buscar usuario existente
        usuario_existente = await UserRepository.find_by_id(session, user_id)
        if not usuario_existente:
            raise ValueError(f"Usuario no encontrado con ID: {user_id}")

        # 2. Aplicar el cambio de permiso
        usuario_existente.permiso = permiso

        # 3. Solo encriptar si viene una contraseña nueva
        if raw_password:
            usuario_existente.password = await get_password_hash(raw_password)

        # 4. Sincronizar la Authority. Buscamos si ya existe.
        stmt = select(Authorities).where(Authorities.username == usuario_existente.username)
        result = await session.execute(stmt)
        authority_existente = result.scalar_one_or_none()

        if authority_existente:
            authority_existente.role = f"ROLE_{permiso}"
        else:
            nueva_autoridad = Authorities(username=usuario_existente.username, role=f"ROLE_{permiso}")
            session.add(nueva_autoridad)

        # 5. Guardamos todos los cambios en base de datos
        await session.commit()
        return usuario_existente

    @staticmethod
    async def authenticate_user(session: AsyncSession, username: str, raw_password: str) -> Users | None:
        """Equivale al proceso interno de AuthenticationManager de Spring Security."""
        # 1. Buscamos el usuario por su nombre
        user = await UserRepository.find_by_username(session, username)
        if not user:
            return None

        # 2. Comparamos la contraseña en texto plano con el hash de la BD
        password_matches = await verify_password(raw_password, user.password)
        if not password_matches:
            return None
        if not user.enabled:
            return None

        # 3. Si existe y la contraseña coincide, devolvemos el usuario
        return user