# app/models/articulo_model.py
from typing import Optional
from sqlalchemy import Boolean, Float, Integer, String, Double
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Articulos(Base):
    __tablename__ = "articulos"

    # La nulabilidad NO se declara: SQLAlchemy la deduce de la anotacion Mapped[...]
    #   Mapped[str]           -> NOT NULL      (equivale a @Column(nullable = false))
    #   Mapped[Optional[str]] -> admite NULL   (el defecto de Hibernate)
    # Una sola fuente de verdad: el tipo Python y la columna no pueden contradecirse.

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100))
    categoria: Mapped[str] = mapped_column(String(50))
    # INCORRECTO: Double es el tipo SQL, no el de Python (el atributo guarda un numero)
    # precio: Mapped[Double] = mapped_column(Double)
    precio: Mapped[float] = mapped_column(Double)
    cantidad: Mapped[int] = mapped_column(Integer)
    codigo: Mapped[str] = mapped_column(String(13), unique=True)
    version: Mapped[int] = mapped_column(Integer)

    # Campos opcionales (nulables)
    aemps_code: Mapped[Optional[str]] = mapped_column(String(10))
    laboratorio: Mapped[Optional[str]] = mapped_column(String(100))

    # Borrado logico, como users.enabled (user_model.py:19). Un DELETE fisico
    # se llevaba las ventas por fk_articulos_ventas (ON DELETE CASCADE); con
    # enabled=False el articulo deja de verse y su historial se queda.
    # Columna anadida a mano en Aiven el 2026-10-18 (ddl-auto=none: nadie la
    # crea solo). Mapped[bool] -> NOT NULL, igual que en la BD.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Habilita el bloqueo optimista que tenías con @Version en Spring
    __mapper_args__ = {"version_id_col": version}
