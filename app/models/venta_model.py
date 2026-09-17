# app/models/venta_model.py
from datetime import date, time
from sqlalchemy import Date, Float, Integer, String, Time, Double
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Ventas(Base):
    __tablename__ = "ventas"

    # La nulabilidad NO se declara: SQLAlchemy la deduce de la anotacion Mapped[...]
    #   Mapped[str]           -> NOT NULL      (equivale a @Column(nullable = false))
    #   Mapped[Optional[str]] -> admite NULL   (el defecto de Hibernate)
    # Una sola fuente de verdad: el tipo Python y la columna no pueden contradecirse.

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date)
    hora: Mapped[time] = mapped_column(Time)
    username: Mapped[str] = mapped_column("id_username", String(50))
    dnicliente: Mapped[str] = mapped_column(String(20))
    nameproducto: Mapped[str] = mapped_column(String(100))
    cantidad: Mapped[int] = mapped_column(Integer)
    # INCORRECTO: Double es el tipo SQL, no el de Python (el atributo guarda un numero)
    # importe: Mapped[Double] = mapped_column(Double)
    importe: Mapped[float] = mapped_column(Double)
    codigo: Mapped[str] = mapped_column(String(13))
