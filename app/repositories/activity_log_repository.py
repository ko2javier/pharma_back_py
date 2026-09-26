# app/repositories/activity_log_repository.py
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log_model import ActivityLog


class ActivityLogRepository:

    @staticmethod
    async def save(session: AsyncSession, log: ActivityLog) -> ActivityLog:
        """Equivalente a guardar un nuevo registro (insert)."""
        session.add(log)
        await session.flush()
        await session.refresh(log)
        return log

    @staticmethod
    async def find_all_ordered(session: AsyncSession) -> Sequence[ActivityLog]:
        """Equivalente a findAllByOrderByFechaDescHoraDesc()"""
        stmt = select(ActivityLog).order_by(
            ActivityLog.fecha.desc(),
            ActivityLog.hora.desc()
        )
        result = await session.execute(stmt)
        return result.scalars().all()