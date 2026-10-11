# tests/test_security.py
#
# NIVEL 1 de ESTRUCTURA §9: unitario puro, sin HTTP y sin base de datos. Es el
# JUnit sin @SpringBootTest — se llama a la funcion y se mira lo que devuelve.
#
# Aqui vive el contrato del token (§6 bis), que es lo unico del backend que el
# frontend en produccion lee POR DENTRO: el Angular decodifica el JWT para
# saber el rol y pintar el menu. Un claim mal escrito no rompe ningun endpoint
# y rompe la aplicacion entera.
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_HOURS,
    ALGORITHM,
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)

settings = get_settings()


# -------------------------------------------------------------------------
# El token que se emite
# -------------------------------------------------------------------------
def test_el_token_lleva_los_cuatro_claims_del_contrato():
    token = create_access_token(username="ko2", role="SUPERADMIN")
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])

    # Ni uno mas ni uno menos: el Angular lee 'role' y deps.py lee 'sub'.
    assert set(claims) == {"sub", "role", "iat", "exp"}
    assert claims["sub"] == "ko2"
    assert claims["role"] == "SUPERADMIN"


def test_el_rol_va_sin_el_prefijo_ROLE_():
    """Spring antepone ROLE_ en las authorities, pero DENTRO del token va crudo.

    Si aqui saliera "ROLE_SUPERADMIN", require_role("SUPERADMIN") de deps.py
    no dejaria entrar a nadie en /activity-log y no haria ningun ruido: un 403
    permanente. Es el mismo error que ya se colo una vez leyendo el claim
    "rol" en vez de "role".
    """
    token = create_access_token(username="ko2", role="SUPERADMIN")
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    assert claims["role"] == "SUPERADMIN"
    assert not claims["role"].startswith("ROLE_")


def test_el_token_caduca_a_las_diez_horas():
    """El Java emite 10 h (JwtUtil). El primer borrador de este proyecto puso
    24: un fallo de contrato que alargaba la sesion al doble sin que nadie lo
    notara."""
    antes = datetime.now(timezone.utc)
    token = create_access_token(username="ko2", role="ADMIN")
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])

    caducidad = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    esperada = antes + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

    assert ACCESS_TOKEN_EXPIRE_HOURS == 10
    # Margen de 5 s: entre el "antes" y el jwt.encode pasa un rato.
    assert abs((caducidad - esperada).total_seconds()) < 5


def test_el_sub_viaja_como_cadena():
    # PyJWT 2.10+ RECHAZA un 'sub' que no sea str al decodificar. Con la firma
    # vieja (un dict libre) nada obligaba a que lo fuera.
    token = create_access_token(username="ko2", role="ADMIN")
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    assert isinstance(claims["sub"], str)


# -------------------------------------------------------------------------
# El token que se valida: los cinco rechazos
# -------------------------------------------------------------------------
def test_decodifica_un_token_bueno():
    token = create_access_token(username="ko2", role="ADMIN")
    claims = decode_access_token(token)
    assert claims["sub"] == "ko2"


def test_rechaza_un_token_manipulado():
    token = create_access_token(username="ko2", role="SELLER")
    # Se cambia un caracter del payload: la firma deja de cuadrar.
    cabecera, payload, firma = token.split(".")
    manipulado = f"{cabecera}.{payload[:-2]}XY.{firma}"

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(manipulado)


def test_rechaza_un_token_firmado_con_otro_secreto():
    # El escenario real: alguien fabrica su propio token con rol SUPERADMIN.
    ajeno = jwt.encode(
        {"sub": "intruso", "role": "SUPERADMIN",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        # 32+ bytes, o PyJWT avisa con InsecureKeyLengthWarning y ensucia la
        # salida de la bateria con un problema del test, no del codigo.
        "otro-secreto-cualquiera-de-32-bytes-o-mas",
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(ajeno)


def test_rechaza_un_token_caducado():
    # Para esto existe el parametro expires_delta: es una desviacion
    # deliberada respecto al Java, puesta SOLO para poder escribir este test.
    caducado = create_access_token(
        username="ko2", role="ADMIN", expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(caducado)


def test_la_caducada_es_una_subclase_de_la_generica():
    """Por que importa: deps.py captura jwt.InvalidTokenError a secas y con eso
    cubre tambien la caducada. Si algun dia hiciera falta distinguirlas (un 401
    con 'sesion expirada'), hay que capturar ExpiredSignatureError ANTES o no
    se llegaria nunca a esa rama."""
    assert issubclass(jwt.ExpiredSignatureError, jwt.InvalidTokenError)


def test_rechaza_alg_none():
    """El ataque clasico: un token sin firma diciendo que no hace falta
    firmarlo. PyJWT solo lo para porque decode_access_token fija
    algorithms=["HS256"]."""
    sin_firma = jwt.encode(
        {"sub": "intruso", "role": "SUPERADMIN",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        key="",
        algorithm="none",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(sin_firma)


def test_rechaza_un_token_sin_sub():
    """Sin require=["exp","sub"], PyJWT devolveria un dict incompleto y el
    payload["sub"] de deps.py reventaria con KeyError -> 500 en vez de 401."""
    cojo = jwt.encode(
        {"role": "ADMIN", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(cojo)


def test_rechaza_un_token_sin_exp():
    eterno = jwt.encode(
        {"sub": "ko2", "role": "ADMIN"}, settings.jwt_secret, algorithm=ALGORITHM
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(eterno)


# -------------------------------------------------------------------------
# bcrypt
# -------------------------------------------------------------------------
# Un hash real generado con rounds=10 y prefijo 2a, el mismo formato que
# escribio Spring Security en la tabla 'users' de Aiven. Esta escrito a pelo y
# no generado en el test a proposito: prueba que los hashes QUE YA EXISTEN
# siguen validando, que es lo que permitio no migrar ninguna contrasena.
HASH_ESTILO_SPRING = "$2a$10$0tfTx10wCB2xVH37708p0.rhUOyPSdMpqh3eSv7vWP/D9ecVYjAOO"


async def test_verifica_un_hash_de_los_que_escribio_spring():
    assert await verify_password("1234", HASH_ESTILO_SPRING) is True


async def test_no_verifica_una_contrasena_equivocada():
    assert await verify_password("12345", HASH_ESTILO_SPRING) is False


async def test_el_hash_que_genera_python_tiene_el_formato_de_spring():
    """El defecto de la libreria Python es $2b$12$: compatible, pero 198 ms por
    hash en vez de 50, y dejaria dos costes mezclados en la misma tabla."""
    hash_nuevo = await get_password_hash("Pass1234!")
    assert hash_nuevo.startswith("$2a$10$")
    assert len(hash_nuevo) == 60


async def test_el_hash_generado_se_verifica_a_si_mismo():
    hash_nuevo = await get_password_hash("Pass1234!")
    assert await verify_password("Pass1234!", hash_nuevo) is True
    assert await verify_password("otra", hash_nuevo) is False


async def test_dos_hashes_de_la_misma_contrasena_son_distintos():
    # La sal va dentro del hash. Si salieran iguales, bcrypt estaria mal usado
    # y dos usuarios con la misma clave serian identificables en la tabla.
    uno = await get_password_hash("Pass1234!")
    otro = await get_password_hash("Pass1234!")
    assert uno != otro
