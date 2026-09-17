# app/models/user_model.py
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Users(Base):
    __tablename__ = "users"

    # La nulabilidad NO se declara: SQLAlchemy la deduce de la anotacion Mapped[...]
    #   Mapped[str]           -> NOT NULL      (equivale a @Column(nullable = false))
    #   Mapped[Optional[str]] -> admite NULL   (el defecto de Hibernate)
    # Una sola fuente de verdad: el tipo Python y la columna no pueden contradecirse.

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    permiso: Mapped[str] = mapped_column(String(50))
