# app/repositories/venta_cancelada_repository.py
# ← VentaCanceladaRepository.java, que es un JpaRepository<VentaCancelada, Long>
# sin un solo método declarado ("Spring hace la magia", dice su comentario). La
# magia son estos dos: save() y findAll().
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.venta_cancelada_model import VentaCancelada


class VentaCanceladaRepository:

    @staticmethod
    async def save(session: AsyncSession, cancelacion: VentaCancelada) -> VentaCancelada:
        session.add(cancelacion)
        await session.flush()
        return cancelacion

    # FALTABA. La escribiste con save() nada más, y sin esto no se puede hacer
    # GET /cancelaciones: VentaCanceladaService.obtenerTodas() es un findAll()
    # pelado (VentaCanceladaService.java:24).
    @staticmethod
    async def find_all(session: AsyncSession) -> Sequence[VentaCancelada]:
        stmt = select(VentaCancelada)
        result = await session.execute(stmt)
        return result.scalars().all()
