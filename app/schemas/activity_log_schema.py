# app/schemas/activity_log_schema.py
from datetime import date, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ActivityLogOut(BaseModel):
    """← ActivityLog.java — salida de GET /activity-log/all (solo SUPERADMIN).

    Solo hay schema de salida: el historial nunca se escribe desde HTTP, lo escribe
    el propio backend con activity_log_service.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    username: str
    action: str = Field(examples=["LOGIN_SUCCESS"])
    detail: Optional[str] = None
    # La columna es ip_address y el campo Java era ipAddress: el JSON siempre fue camelCase
    ip_address: Optional[str] = Field(default=None, alias="ipAddress")
    fecha: date
    hora: time
