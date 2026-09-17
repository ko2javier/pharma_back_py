# app/schemas/venta_schema.py
from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field


class VentaCreate(BaseModel):
    """← VentaDTO.java — cuerpo de POST /ventas/registrar y de /ventas/registrar/list.

    No lleva fecha, hora ni username: los pone el servidor (la fecha/hora del sistema
    y el usuario autenticado del token), igual que hace VentaService.
    """

    dnicliente: str = Field(examples=["12345678A"])
    nameproducto: str = Field(examples=["Ibuprofeno 600mg"])
    cantidad: int = Field(examples=[2])
    importe: float = Field(examples=[25.90], description="Importe total de la venta (EUR)")
    codigo: str = Field(examples=["8470001234567"])


class VentaOut(BaseModel):
    """Respuesta de los endpoints de /ventas.

    'username' es el nombre del atributo Python; la columna se llama id_username,
    pero el JSON que veia el frontend siempre fue "username" (Jackson serializa el
    campo Java, no la columna). Se mantiene igual.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    hora: time
    username: str
    dnicliente: str
    nameproducto: str
    cantidad: int
    importe: float
    codigo: str
