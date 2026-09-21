# app/core/security.py
#
# Equivale a JwtUtil.java (firmar y validar tokens) + al BCryptPasswordEncoder
# que SecurityConfig.java declaraba como @Bean.
#
# Aquí NO se importa nada de FastAPI a propósito: este módulo no sabe que existe
# el HTTP, igual que tu JwtUtil no sabía nada de peticiones. Traducir un token
# inválido a un 401 es trabajo de api/deps.py (paso 7).

import asyncio
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"

# INCORRECTO (lo que había antes):
#     # Ajusta el tiempo de expiración al que tuvieras en Spring Boot (ej. 24 horas)
#     ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
#
# No era 24 horas: el JwtUtil.java pone
#     new Date(System.currentTimeMillis() + 1000 * 60 * 60 * 10)  // 10 horas
# Se comprobó decodificando un token de la versión anterior: "caduca en 24.0
# horas". Doblar la vida de un token no rompe al frontend, pero alarga el daño
# si se filtra, así que se iguala al Java. En horas y no en minutos porque así
# se lee igual que el original.
ACCESS_TOKEN_EXPIRE_HOURS = 10

# Coste y formato del hash, los mismos que BCryptPasswordEncoder:
# prefijo $2a$ y 10 rondas. Ver el comentario de get_password_hash.
BCRYPT_ROUNDS = 10
BCRYPT_PREFIX = b"2a"


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Comprueba que la contraseña en texto plano coincide con el hash de la BD."""
    # bcrypt requiere bytes, así que codificamos los strings a utf-8
    password_bytes = plain_password.encode("utf-8")
    hash_bytes = hashed_password.encode("utf-8")

    # El to_thread es TUYO y se queda: medido con cuatro hashes seguidos,
    #     llamada directa -> el bucle de eventos se para 821 ms
    #     con to_thread   -> se para 22 ms
    # bcrypt es CPU pura y aquí no hay un pool de hilos como el de Tomcat: un
    # solo hilo atiende TODAS las peticiones, así que un login bloquearía la API
    # entera, no sólo al que hace login. Es el equivalente a un @Async.
    #
    # Nota: los hashes que ya están en Aiven son $2a$10$ y se validan sin tocar
    # nada (comprobado generando uno con prefix=2a y pasándolo por esta función).
    return await asyncio.to_thread(bcrypt.checkpw, password_bytes, hash_bytes)


async def get_password_hash(password: str) -> str:
    """Genera un hash BCrypt para una nueva contraseña.

    Ojo con una trampa de bcrypt: trunca la contraseña a 72 bytes en silencio.
    No es problema aquí (el Java hacía lo mismo, es la propia librería), pero
    conviene saberlo antes de perder una tarde con contraseñas larguísimas.
    """
    password_bytes = password.encode("utf-8")

    # INCORRECTO (lo que había antes):
    #     hashed_bytes = await asyncio.to_thread(bcrypt.hashpw, password_bytes, bcrypt.gensalt())
    #
    # gensalt() sin argumentos usa los valores por defecto de la librería
    # Python, que NO son los del Java: salían hashes $2b$12$ donde
    # BCryptPasswordEncoder produce $2a$10$. No rompe nada —Spring valida $2b$ y
    # esta función valida $2a$—, pero tenía dos efectos molestos:
    #   1. 198 ms por hash en vez de 50 ms (medido), en cada alta de usuario.
    #   2. la tabla users acabaría con dos costes distintos mezclados.
    hashed_bytes = await asyncio.to_thread(
        bcrypt.hashpw, password_bytes, bcrypt.gensalt(rounds=BCRYPT_ROUNDS, prefix=BCRYPT_PREFIX)
    )

    # Devolvemos un string normal para guardarlo en la base de datos
    return hashed_bytes.decode("utf-8")


def create_access_token(
    username: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Genera el token JWT. Equivale a tu JwtUtil.generateToken(username, rol).

    INCORRECTO (lo que había antes):
        def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
            to_encode = data.copy()

    El dict libre dejaba el contrato en este docstring y en ningún sitio más, o
    sea en ninguno: nada impedía escribir {"rol": ...} en vez de {"role": ...}.
    El token saldría firmado y válido, el frontend dejaría de ver el rol, y no
    fallaría nada ni aquí ni en los tests. Con los parámetros explícitos ese
    error es imposible: Python te para en la llamada.

    Es además la misma firma que el Java —generateToken(String username,
    String rol)—, así que los dos backends se leen igual.

    Claims que emite, y hay que respetarlos porque el frontend en producción lee
    el rol del propio token:
        sub  -> username
        role -> users.permiso TAL CUAL, sin el prefijo ROLE_ ("SUPERADMIN")
        iat  -> fecha de emisión
        exp  -> +10 horas

    El sub va como str a propósito: PyJWT 2.10+ rechaza un sub que no lo sea, y
    con el dict libre nada obligaba a que lo fuera (ni a que existiera).

    Si algún día hace falta meter un claim más, se añade como parámetro con su
    valor por defecto. Si llegaran a ser muchos, el paso siguiente sería un
    TypedDict de claims, no volver al dict abierto.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # INCORRECTO (lo que había antes): timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        # con la constante puesta a 60 * 24.
        expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

    # AÑADIDO el iat, que faltaba: el Java hace setIssuedAt(new Date()) y los
    # claims que salían eran sólo ['exp', 'role', 'sub']. Nadie lo valida, pero
    # así los dos backends emiten tokens idénticos.
    #
    # datetime.now(timezone.utc) y no utcnow(): utcnow() está deprecado desde
    # Python 3.12 y además devuelve una fecha SIN zona horaria, que es la receta
    # para un token que caduca con horas de diferencia según el servidor.
    to_encode = {
        "sub": username,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }

    # jwt.encode es muy rápido, por lo que puede ser una función síncrona normal.
    # (En PyJWT 2.x devuelve ya un str; en la 1.x devolvía bytes.)
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Valida la firma y la expiración, y devuelve los claims.

    FALTABA: sólo se firmaban tokens, no se validaban. Es la mitad que necesita
    api/deps.py (paso 7), el equivalente a extractUsername() + isTokenExpired()
    del JwtUtil, pero en una sola llamada porque PyJWT ya comprueba el exp.

    Dos diferencias a favor respecto al Java:
      - algorithms=[ALGORITHM] es obligatorio en PyJWT. Sin fijar el algoritmo,
        un atacante podría mandar un token con alg=none y colarse.
      - require=["exp", "sub"] rechaza un token sin esos claims en vez de
        devolver un dict incompleto que reventaría más adelante.

    NO captura las excepciones a propósito: deja subir jwt.ExpiredSignatureError
    (token caducado) y jwt.InvalidTokenError (firma mala, manipulado, claims que
    faltan). Quien las traduce a un 401 con su mensaje es deps.py, que es el que
    sabe de HTTP. ExpiredSignatureError hereda de InvalidTokenError, así que allí
    hay que capturarla ANTES si se quieren distinguir.
    """
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
