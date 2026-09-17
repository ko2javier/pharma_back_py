# app/models/__init__.py

# 1. Importamos el Base
from .base import Base

# 2. Importamos todos los modelos para que SQLAlchemy (y su Base.metadata)
# se enteren de que estas tablas existen.
from .user_model import Users
from .authority_model import Authorities
from .articulo_model import Articulos
from .venta_model import Ventas
from .venta_cancelada_model import VentaCancelada, CancellationStatus
from .activity_log_model import ActivityLog

# Definimos qué se exporta si alguien hace `from app.models import *`
__all__ = [
    "Base",
    "Users",
    "Authorities",
    "Articulos",
    "Ventas",
    "VentaCancelada",
    "CancellationStatus",
    "ActivityLog",
]