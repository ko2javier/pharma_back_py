# app/schemas/ia_schema.py
# Contrato con el microservicio de IA. Ojo: aqui el JSON es snake_case, no camelCase,
# porque el microservicio destino es Python. En Java habia que forzarlo a mano con
# @JsonProperty("busqueda_usuario"); en Python los nombres ya salen asi solos.
from pydantic import BaseModel, Field


class MedicamentoAemps(BaseModel):
    """← MedicamentoAempsDTO.java — un medicamento del catalogo AEMPS, ya limpio."""

    id: str = Field(examples=["67031"], description="Numero de registro AEMPS (nregistro)")
    nombre: str = Field(examples=["IBUPROFENO KERN PHARMA 600 MG"])


class IaMatchRequest(BaseModel):
    """← MatchRequestDTO.java — cuerpo del POST {IA_SERVICE_URL}/api/v1/ia/match."""

    busqueda_usuario: str = Field(examples=["ibuprofeno 600"])
    lista_limpia: list[MedicamentoAemps]
