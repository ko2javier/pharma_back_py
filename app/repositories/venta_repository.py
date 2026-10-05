# app/repositories/venta_repository.py
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.venta_model import Ventas

class VentaRepository:

    @staticmethod
    async def find_all(session: AsyncSession) -> Sequence[Ventas]:
        stmt = select(Ventas)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def find_by_username(session: AsyncSession, username: str) -> Sequence[Ventas]:
        """Equivalente a List<Ventas> findByusername(String username)"""
        stmt = select(Ventas).where(Ventas.username == username)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def find_by_id(session: AsyncSession, venta_id: int) -> Ventas | None:
        return await session.get(Ventas, venta_id)

    @staticmethod
    async def save(session: AsyncSession, venta: Ventas) -> Ventas:
        session.add(venta)
        # Quitado: await session.refresh(venta)
        #
        # flush() manda el INSERT y SQLAlchemy ya escribe de vuelta en el objeto
        # el id que generó MySQL, así que el refresh era un SELECT extra para
        # releer lo que ya teníamos. Comprobado ejecutando:
        #     Ventas.id tras SOLO flush -> 1
        # Sigue haciendo falta cuando la columna la rellena el SERVIDOR y Python
        # no puede saberlo (un DEFAULT CURRENT_TIMESTAMP, un trigger): ahí el
        # objeto se quedaría con None. En este proyecto no hay ninguna.
        await session.flush()
        return venta

    @staticmethod
    async def delete(session: AsyncSession, venta: Ventas) -> None:
        await session.delete(venta)
        await session.flush()

