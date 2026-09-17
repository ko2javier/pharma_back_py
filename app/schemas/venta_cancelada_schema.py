# app/schemas/venta_cancelada_schema.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# El enum vive en el modelo y se reutiliza aqui: es el mismo conjunto de valores
# que acepta la columna, no tiene sentido duplicarlo.
from app.models.venta_cancelada_model import CancellationStatus


class VentaCanceladaCreate(BaseModel):
    """Cuerpo de POST /cancelaciones.

    En Java el controlador recibia la entidad VentaCancelada entera, con su id
    incluido. Aqui el id no se acepta: lo genera la base de datos, y dejar que
    el cliente lo mande es una puerta abierta a sobrescribir filas ajenas.
    """

    model_config = ConfigDict(populate_by_name=True)

    nombre_producto: Optional[str] = Field(default=None, alias="nombreProducto")
    cantidad: int
    importe: Optional[float] = None
    responsable: Optional[str] = Field(default=None, examples=["admin"])
    status: Optional[CancellationStatus] = Field(default=None, examples=["CANCELLED"])
    # Si no viene, la rellena el modelo con datetime.now (como el constructor de Java)
    fecha: Optional[datetime] = None


class VentaCanceladaOut(BaseModel):
    """Respuesta de GET /cancelaciones y de POST /cancelaciones."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    nombre_producto: Optional[str] = Field(default=None, alias="nombreProducto")
    cantidad: int
    importe: Optional[float] = None
    responsable: Optional[str] = None
    fecha: datetime
    status: Optional[CancellationStatus] = None
