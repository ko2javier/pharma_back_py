# app/schemas/user_schema.py
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    """← Insert_User_DTO.java — cuerpo de POST /users/insert."""

    username: str = Field(examples=["farmaceutico01"])
    password: str = Field(examples=["Pass1234!"])
    permiso: str = Field(examples=["SELLER"], description="SELLER, ADMIN o SUPERADMIN")


class UserUpdate(BaseModel):
    """Cuerpo de PUT /users/update.

    Java recibe aqui la entidad Users entera, pero UserService solo lee id, permiso
    y password. Se declara solo eso: lo demas se ignoraba de todas formas.
    La password es opcional — si viene vacia, se conserva la que ya tenia.
    """

    id: int
    permiso: str = Field(examples=["ADMIN"])
    password: Optional[str] = Field(default=None, examples=["NuevaPass1!"])


class UserOut(BaseModel):
    """Respuesta con datos de usuario. Nunca incluye la password.

    Equivale al @JsonProperty(access = WRITE_ONLY) de Users.java: el campo entra
    en las peticiones pero jamas sale en las respuestas.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    enabled: bool
    permiso: str
