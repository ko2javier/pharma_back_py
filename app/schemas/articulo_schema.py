# app/schemas/articulo_schema.py
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ArticuloCreate(BaseModel):
    """← Insert_DTO.java — cuerpo de POST /articulos/insert.

    No lleva 'codigo': lo genera el servicio (generarCodigoUnico de ArticuloService).
    """

    model_config = ConfigDict(populate_by_name=True)

    nombre: str = Field(examples=["Ibuprofeno 600mg"])
    categoria: str = Field(examples=["Antiinflamatorio"])
    precio: float = Field(examples=[12.95], description="Precio de venta al publico (EUR)")
    cantidad: int = Field(examples=[50], description="Unidades disponibles en stock")
    # alias: el JSON que manda el frontend usa camelCase, como lo serializaba Jackson
    aemps_code: Optional[str] = Field(default=None, alias="aempsCode", examples=["67031"])
    laboratorio: Optional[str] = Field(default=None, examples=["Kern Pharma"])


class ArticuloUpdate(BaseModel):
    """← UpdateDTO.java — se reutiliza en dos endpoints distintos:

    - PUT /articulos/updateStock  (lote): solo usa 'codigo' y 'cantidadVendida'.
    - PUT /articulos/updateItem:          solo usa 'codigo', 'cantidad' y 'precio'.

    Por eso todo es opcional menos 'codigo', que es la clave de busqueda en los dos.
    En Java los int/double no declarados llegaban como 0; aqui llegan como 0 tambien,
    para no cambiar el comportamiento.
    """

    model_config = ConfigDict(populate_by_name=True)

    codigo: str = Field(examples=["8470001234567"])
    cantidad_vendida: int = Field(default=0, alias="cantidadVendida")
    cantidad: int = 0
    precio: float = 0.0
    nombre: Optional[str] = None
    categoria: Optional[str] = None


class ArticuloAempsLink(BaseModel):
    """Cuerpo de PATCH /articulos/{id}/aemps.

    En Java era un Map<String, String> anonimo; aqui queda documentado en el /docs.
    """

    model_config = ConfigDict(populate_by_name=True)

    aemps_code: Optional[str] = Field(default=None, alias="aempsCode", examples=["67031"])
    laboratorio: Optional[str] = Field(default=None, examples=["Kern Pharma"])


class ArticuloOut(BaseModel):
    """Respuesta de todos los endpoints de /articulos.

    Java devolvia la entidad Articulos directamente y Jackson la serializaba; aqui
    se declara explicitamente que sale, que es lo que documenta el /docs.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    nombre: str
    categoria: str
    precio: float
    cantidad: int
    codigo: str
    version: int
    aemps_code: Optional[str] = Field(default=None, alias="aempsCode")
    laboratorio: Optional[str] = None
