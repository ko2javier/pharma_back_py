# tests/test_auth_controller.py
#
# NIVEL 2: contrato HTTP. El service va sustituido, no se toca Aiven.
#
# LO QUE EL JAVA HACE DE VERDAD, leido antes de escribir estos asserts
# (AuthController.java + GlobalExceptionHandler.java + SecurityConfig.java):
#
#   POST /auth/login, credenciales buenas  -> 200 {"token": "..."}   = igual
#   POST /auth/login, credenciales malas   -> 500 {"error": "Error interno
#                                                   del servidor"}
#   POST /auth/login, falta un campo       -> 500 (mismo camino)
#   GET  /auth/protected sin token         -> 200 en texto plano
#
# El 500 del login no es una interpretacion: el catch (AuthenticationException)
# de AuthController.java:91-96 registra el LOGIN_FAILED y hace throw e, y el
# GlobalExceptionHandler no tiene handler para esa excepcion — cae en el
# @ExceptionHandler(Exception.class). Y /auth/protected es publico porque
# SecurityConfig.java:58 hace permitAll() de todo /auth/**.
#
# ESTE BACKEND SE DESVIA A PROPOSITO en los tres casos (401, 422 y 401). Es
# seguro: el Angular no mira el codigo del login, su rama de error es
# "error: () => { toast('Invalid username or password') }"
# (login.component.ts:46), una lambda sin parametro. Los tests afirman el
# contrato del ESPEJO, no el del Java, y por eso lo dicen aqui arriba.
from unittest.mock import AsyncMock

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import ALGORITHM
from app.services.user_service import UserService
from tests.conftest import construir_usuario

settings = get_settings()


@pytest.fixture
def autenticacion(monkeypatch):
    """Sustituye UserService.authenticate_user. Es el @MockBean del service.

    Devuelve el mock para que cada test decida que contesta: la entidad (buen
    login) o None (credenciales malas o usuario deshabilitado — el service los
    une en el mismo None, igual que el Java los une en el mismo 500).
    """
    espia = AsyncMock()
    monkeypatch.setattr(UserService, "authenticate_user", espia)
    return espia


# -------------------------------------------------------------------------
# POST /auth/login
# -------------------------------------------------------------------------
async def test_login_correcto_devuelve_200_y_solo_la_clave_token(client, autenticacion):
    autenticacion.return_value = construir_usuario(username="ko2", permiso="SUPERADMIN")

    r = await client.post("/auth/login", json={"username": "ko2", "password": "1234"})

    assert r.status_code == 200
    # Solo "token": el rol viaja DENTRO del JWT, no como campo aparte. Si
    # algun dia se anadiera otra clave, el Angular no se entera, pero el
    # contrato con el Java si cambia.
    assert set(r.json()) == {"token"}


async def test_el_token_emitido_lleva_el_usuario_y_el_rol_reales(client, autenticacion):
    autenticacion.return_value = construir_usuario(username="ko2", permiso="SUPERADMIN")

    r = await client.post("/auth/login", json={"username": "ko2", "password": "1234"})

    claims = jwt.decode(r.json()["token"], settings.jwt_secret, algorithms=[ALGORITHM])
    assert claims["sub"] == "ko2"
    # El rol sale de la BD (user.permiso), no de lo que mande el cliente.
    assert claims["role"] == "SUPERADMIN"


async def test_login_correcto_registra_LOGIN_SUCCESS(client, autenticacion, log):
    autenticacion.return_value = construir_usuario(username="ko2")

    await client.post("/auth/login", json={"username": "ko2", "password": "1234"})

    assert log.await_count == 1
    _, kwargs = log.await_args
    assert kwargs["action"] == "LOGIN_SUCCESS"
    assert kwargs["username"] == "ko2"


async def test_credenciales_malas_dan_401(client, autenticacion):
    # El Java da 500 aqui (ver la cabecera del fichero). Desviacion deliberada.
    autenticacion.return_value = None

    r = await client.post("/auth/login", json={"username": "ko2", "password": "mala"})

    assert r.status_code == 401
    assert r.json()["detail"] == "Credenciales incorrectas"


async def test_credenciales_malas_registran_LOGIN_FAILED(client, autenticacion, log):
    """El rastro del intento fallido SI existe en el Java, y es lo unico que
    permite ver un ataque de fuerza bruta en el activity_log."""
    autenticacion.return_value = None

    await client.post("/auth/login", json={"username": "fulano", "password": "x"})

    assert log.await_count == 1
    _, kwargs = log.await_args
    assert kwargs["action"] == "LOGIN_FAILED"
    # Se guarda el username INTENTADO, aunque no exista: es el dato util.
    assert kwargs["username"] == "fulano"
    assert kwargs["detail"] == "fulano"


async def test_el_login_fallido_no_emite_ningun_token(client, autenticacion):
    autenticacion.return_value = None
    r = await client.post("/auth/login", json={"username": "ko2", "password": "mala"})
    assert "token" not in r.text


async def test_un_usuario_deshabilitado_entra_por_el_mismo_camino(client, autenticacion):
    # UserService.authenticate_user ya comprueba enabled y devuelve None, asi
    # que desde el controlador es indistinguible de una contrasena mala. A
    # proposito: no se le dice a nadie "esa cuenta existe pero esta bloqueada".
    autenticacion.return_value = None
    r = await client.post("/auth/login", json={"username": "baneado", "password": "1234"})
    assert r.status_code == 401


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"username": "ko2"},
        {"password": "1234"},
        {"username": "ko2", "password": None},
    ],
)
async def test_cuerpo_incompleto_da_422_y_no_llega_al_service(client, autenticacion, cuerpo):
    """Pydantic corta antes del controlador. En el Java esto tambien acababa en
    500, porque el Map<String,String> aceptaba cualquier cosa y el null llegaba
    hasta el AuthenticationManager."""
    r = await client.post("/auth/login", json=cuerpo)

    assert r.status_code == 422
    # Lo importante no es el 422, es que no se gastaron 50 ms de bcrypt ni una
    # conexion de Aiven en una peticion mal formada.
    autenticacion.assert_not_awaited()


async def test_el_login_no_exige_token(client, autenticacion):
    # El huevo y la gallina: si /auth/login pidiera JWT, no habria forma de
    # conseguir el primero. Es el permitAll() de /auth/** del SecurityConfig.
    autenticacion.return_value = construir_usuario()
    r = await client.post("/auth/login", json={"username": "ko2", "password": "1234"})
    assert r.status_code != 401


# -------------------------------------------------------------------------
# GET /auth/protected
# -------------------------------------------------------------------------
async def test_protected_sin_token_da_401(client):
    # En el Java da 200 con o sin token: el nombre del endpoint era mentira
    # (SecurityConfig:58 permitAll de /auth/**). Aqui se cierra de verdad.
    r = await client.get("/auth/protected")
    assert r.status_code == 401


async def test_protected_con_token_saluda_con_el_usuario_y_el_rol(client, autenticar):
    autenticar(username="ko2", permiso="SUPERADMIN")

    r = await client.get("/auth/protected")

    assert r.status_code == 200
    assert "ko2" in r.json()
    assert "SUPERADMIN" in r.json()
