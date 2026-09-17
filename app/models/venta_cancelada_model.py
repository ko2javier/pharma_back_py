# app/models/venta_cancelada_model.py
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import DateTime, Enum as SQLEnum, Float, Integer, String, Double
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CancellationStatus(str, Enum):
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"


class VentaCancelada(Base):
    __tablename__ = "ventas_canceladas"

    # La nulabilidad NO se declara: SQLAlchemy la deduce de la anotacion Mapped[...]
    #   Mapped[str]           -> NOT NULL      (equivale a @Column(nullable = false))
    #   Mapped[Optional[str]] -> admite NULL   (el defecto de Hibernate)
    # Una sola fuente de verdad: el tipo Python y la columna no pueden contradecirse.

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre_producto: Mapped[Optional[str]] = mapped_column(String(100))
    cantidad: Mapped[int] = mapped_column(Integer)
    # INCORRECTO: Double es el tipo SQL, no el de Python (el atributo guarda un numero)
    # importe: Mapped[Optional[Double]] = mapped_column(Double)
    importe: Mapped[Optional[float]] = mapped_column(Double)
    responsable: Mapped[Optional[str]] = mapped_column(String(50))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[Optional[CancellationStatus]] = mapped_column(SQLEnum(CancellationStatus))
