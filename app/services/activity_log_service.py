# app/services/activity_log_service.py
from datetime import date, datetime
from collections.abc import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log_model import ActivityLog
from app.repositories.activity_log_repository import ActivityLogRepository


class ActivityLogService:

    @staticmethod
    async def log(
            session: AsyncSession,
            username: str,
            action: str,
            detail: str | None = None,
            ip: str | None = None
    ) -> None:
        """Registra una acción en el historial de actividad con fecha, hora e IP del cliente."""

        # En Python, sacamos la fecha y hora actual usando el módulo nativo datetime
        registro = ActivityLog(
            username=username,
            action=action,
            detail=detail,
            ip_address=ip,
            fecha=date.today(),  # Equivale a LocalDate.now()
            hora=datetime.now().time()  # Equivale a LocalTime.now()
        )

        await ActivityLogRepository.save(session, registro)

        # Hacemos commit para que el log se guarde inmediatamente en la base de datos
        await session.commit()

    @staticmethod
    async def get_all(session: AsyncSession) -> Sequence[ActivityLog]:
        """Devuelve todos los registros ordenados del más reciente al más antiguo."""
        return await ActivityLogRepository.find_all_ordered(session)
