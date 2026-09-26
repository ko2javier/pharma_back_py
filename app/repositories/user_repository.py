# app/repositories/user_repository.py
# TU VERSIÓN (no estaba mal, sólo desactualizada):
#     from typing import Optional, Sequence
#
# typing.Sequence está en desuso desde Python 3.9: PEP 585 movió los genéricos
# de contenedores a collections.abc, que es donde vive Sequence de verdad
# (typing.Sequence sólo era un alias). database.py ya usa este mismo patrón
# con AsyncGenerator. Y Optional[X] ya no hace falta como import: desde
# Python 3.10 (PEP 604) se escribe X | None directamente en la anotación,
# sin importar nada — es lo que ya hiciste tú mismo en security.py con
# "expires_delta: timedelta | None = None". Optional[X] sigue siendo la
# norma dentro de Mapped[...] (SQLAlchemy) y de los campos Pydantic, así que
# ahí NO se toca; esto es sólo para tipos de parámetros y retornos sueltos.
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_model import Users


class UserRepository:

    # LO VIEJO:
    #     async def find_by_username(session: AsyncSession, username: str) -> Optional[Users]:
    @staticmethod
    async def find_by_username(session: AsyncSession, username: str) -> Users | None:
        """Equivalente a Optional<Users> findByUsername(String username)"""
        stmt = select(Users).where(Users.username == username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    # LO VIEJO:
    #     async def find_by_id(session: AsyncSession, user_id: int) -> Optional[Users]:
    @staticmethod
    async def find_by_id(session: AsyncSession, user_id: int) -> Users | None:
        """Equivalente al findById de JpaRepository"""
        return await session.get(Users, user_id)

    @staticmethod
    async def find_all(session: AsyncSession) -> Sequence[Users]:
        """Equivalente al findAll de JpaRepository"""
        stmt = select(Users)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def save(session: AsyncSession, user: Users) -> Users:
        """Equivalente al save de JpaRepository (para inserts)"""
        session.add(user)
        # El commit se suele hacer en el Service, pero si replicamos el comportamiento
        # exacto de JpaRepository.save(), lo incluimos aquí.
        await session.flush()
        await session.refresh(user)
        return user

    @staticmethod
    async def delete(session: AsyncSession, user: Users) -> None:
        """Equivalente al delete de JpaRepository"""
        await session.delete(user)
        await session.flush()