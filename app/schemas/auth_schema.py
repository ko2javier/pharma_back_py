# app/schemas/auth_schema.py
# Origen: AuthController.java — el login de Java recibe un Map<String, String> suelto,
# aqui se convierte en un contrato explicito que ademas documenta el /docs.
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Cuerpo de POST /auth/login."""

    username: str = Field(examples=["ko2"])
    password: str = Field(examples=["1234"])


class TokenResponse(BaseModel):
    """Respuesta de POST /auth/login.

    Java devuelve unicamente {"token": "..."}; el rol viaja dentro del propio JWT,
    no como campo aparte. Se replica igual para no romper al frontend.
    """

    token: str
