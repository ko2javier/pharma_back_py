# app/repositories/user_repository.py
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