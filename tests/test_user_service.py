# tests/test_user_service.py
#
# NIVEL 1: el service con el repositorio sustituido. Sin HTTP y sin Aiven.
#
# Aqui viven tres cosas que por HTTP solo se verian como un codigo de estado y
# que son justo donde estuvo el fallo:
#
#   * authenticate_user mete tres "no" distintos en el mismo None (usuario
#     inexistente, contrasena mala, usuario deshabilitado). Es deliberado — no
#     se le dice a nadie cual de los tres fue — pero hay que comprobar que los
#     tres caminos existen de verdad y no que uno deja pasar.
#   * El chequeo del duplicado va ANTES de hashear. bcrypt cuesta ~50 ms:
#     hacerlo al reves los regala en cada alta repetida.
#   * El borrado es LOGICO (enabled=False) y no fisico, porque users tiene dos
#     FK con ON DELETE CASCADE y un DELETE real se llevaria el historial de
#     ventas del usuario por delante.
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exceptions.custom import (
    DuplicateResourceException,
    ResourceNotFoundException,
)
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService
from tests.conftest import construir_usuario

# El mismo hash de "1234" que usa test_security.py: formato $2a$10$, el que
# escribio Spring en la tabla de Aiven.
HASH_DE_1234 = "$2a$10$0tfTx10wCB2xVH37708p0.rhUOyPSdMpqh3eSv7vWP/D9ecVYjAOO"


@pytest.fixture
def repo(monkeypatch):
    espias = {}
    for nombre in ("find_by_username", "find_by_id", "find_all", "save", "delete"):
        espia = AsyncMock()
        monkeypatch.setattr(UserRepository, nombre, espia)
        espias[nombre] = espia
    return espias


def fingir_authority(sesion, authority=None):
    """Monta session.execute(...).scalar_one_or_none() -> authority.

    actualizar_usuario no pasa por el repositorio para esta consulta: hace el
    select(Authorities) a mano contra la sesion, asi que hay que fingirlo
    aqui.

    Y hay que montarlo con MagicMock a mano: los hijos de un AsyncMock son
    AsyncMock tambien, asi que result.scalar_one_or_none() devolveria una
    CORUTINA en vez de la fila, y el service se come un
        AttributeError: 'coroutine' object has no attribute 'role'
    que no se parece en nada al problema real. scalar_one_or_none() es
    sincrona (lo async fue el execute), y el mock tiene que serlo tambien.
    """
    resultado = MagicMock()
    resultado.scalar_one_or_none.return_value = authority
    sesion.execute.return_value = resultado
    return resultado


# -------------------------------------------------------------------------
# authenticate_user: el AuthenticationManager de Spring
# -------------------------------------------------------------------------
async def test_login_correcto_devuelve_el_usuario(sesion, repo):
    usuario = construir_usuario(username="ko2")
    usuario.password = HASH_DE_1234
    repo["find_by_username"].return_value = usuario

    resultado = await UserService.authenticate_user(sesion, "ko2", "1234")

    assert resultado is usuario


async def test_usuario_inexistente_devuelve_None(sesion, repo):
    repo["find_by_username"].return_value = None

    assert await UserService.authenticate_user(sesion, "fulano", "1234") is None


async def test_contrasena_equivocada_devuelve_None(sesion, repo):
    usuario = construir_usuario()
    usuario.password = HASH_DE_1234
    repo["find_by_username"].return_value = usuario

    assert await UserService.authenticate_user(sesion, "ko2", "12345") is None


async def test_un_usuario_deshabilitado_no_entra_aunque_acierte_la_contrasena(sesion, repo):
    """Es el efecto del borrado logico: la fila sigue ahi, con su hash bueno,
    y aun asi no se puede entrar. Si este test se cayera, un usuario "borrado"
    seguiria teniendo acceso."""
    usuario = construir_usuario(enabled=False)
    usuario.password = HASH_DE_1234
    repo["find_by_username"].return_value = usuario

    assert await UserService.authenticate_user(sesion, "ko2", "1234") is None


async def test_un_usuario_inexistente_no_gasta_bcrypt(sesion, repo):
    """Corta en el primer if. Importa porque bcrypt son ~50 ms de CPU: con
    usuarios inventados, comprobar la contrasena de un usuario que no existe
    seria un modo barato de tumbar la API."""
    repo["find_by_username"].return_value = None

    await UserService.authenticate_user(sesion, "fulano", "1234")

    # No hay nada que mockear para comprobarlo: si hubiera hasheado, habria
    # tenido que leer user.password de un None y habria reventado.
    repo["find_by_username"].assert_awaited_once()


# -------------------------------------------------------------------------
# crear_usuario
# -------------------------------------------------------------------------
async def test_crear_usuario_guarda_el_hash_y_nunca_la_contrasena(sesion, repo):
    repo["find_by_username"].return_value = None

    nuevo = await UserService.crear_usuario(sesion, "nuevo", "Pass1234!", "SELLER")

    assert nuevo.password != "Pass1234!"
    assert nuevo.password.startswith("$2a$10$")
    repo["save"].assert_awaited_once()


async def test_crear_usuario_duplicado_lanza_la_excepcion_del_409(sesion, repo):
    repo["find_by_username"].return_value = construir_usuario(username="ko2")

    with pytest.raises(DuplicateResourceException):
        await UserService.crear_usuario(sesion, "ko2", "x", "SELLER")

    repo["save"].assert_not_awaited()
    sesion.commit.assert_not_awaited()


async def test_el_duplicado_se_comprueba_ANTES_de_hashear(sesion, repo):
    """El orden importa: bcrypt cuesta ~50 ms y un alta repetida no tiene por
    que pagarlos. Se comprueba de forma indirecta pero solida: si hubiera
    hasheado primero, el find_by_username seguiria llamandose, pero el save
    tambien se habria preparado. Lo que se fija aqui es que la excepcion sale
    sin haber tocado nada mas."""
    repo["find_by_username"].return_value = construir_usuario()

    with pytest.raises(DuplicateResourceException):
        await UserService.crear_usuario(sesion, "ko2", "x", "SELLER")

    assert repo["find_by_username"].await_count == 1
    sesion.add.assert_not_called()


async def test_crear_usuario_tambien_escribe_la_fila_de_authorities(sesion, repo):
    """La tabla authorities la comparte con el backend Java, que es quien la
    lee en su login (JdbcUserDetailsManager). Si no se escribiera, el usuario
    existiria en Python y no podria entrar en el Java, y al reves — la BD es
    la misma."""
    repo["find_by_username"].return_value = None

    await UserService.crear_usuario(sesion, "nuevo", "x", "SELLER")

    sesion.add.assert_called_once()
    autoridad = sesion.add.call_args.args[0]
    # Y AQUI SI va el prefijo ROLE_, al contrario que en el JWT: es lo que
    # espera Spring Security al leer la tabla.
    assert autoridad.role == "ROLE_SELLER"
    assert autoridad.username == "nuevo"


# -------------------------------------------------------------------------
# actualizar_usuario
# -------------------------------------------------------------------------
async def test_actualizar_sin_password_conserva_el_hash_anterior(sesion, repo):
    usuario = construir_usuario(id=7, permiso="SELLER")
    usuario.password = HASH_DE_1234
    repo["find_by_id"].return_value = usuario
    fingir_authority(sesion, None)

    await UserService.actualizar_usuario(sesion, user_id=7, permiso="ADMIN", raw_password=None)

    assert usuario.permiso == "ADMIN"
    assert usuario.password == HASH_DE_1234


async def test_actualizar_con_password_la_vuelve_a_hashear(sesion, repo):
    usuario = construir_usuario(id=7)
    usuario.password = HASH_DE_1234
    repo["find_by_id"].return_value = usuario
    fingir_authority(sesion, None)

    await UserService.actualizar_usuario(sesion, user_id=7, permiso="ADMIN", raw_password="NuevaPass1!")

    assert usuario.password != HASH_DE_1234
    assert usuario.password.startswith("$2a$10$")


async def test_una_password_vacia_cuenta_como_no_cambiarla(sesion, repo):
    """El service usa "if raw_password", no "if raw_password is not None": una
    cadena vacia del formulario no borra la contrasena del usuario."""
    usuario = construir_usuario(id=7)
    usuario.password = HASH_DE_1234
    repo["find_by_id"].return_value = usuario
    fingir_authority(sesion, None)

    await UserService.actualizar_usuario(sesion, user_id=7, permiso="ADMIN", raw_password="")

    assert usuario.password == HASH_DE_1234


async def test_actualizar_un_usuario_inexistente_lanza_el_404(sesion, repo):
    """Esto era un ValueError hasta el paso 9 bis — sin handler, caia en el
    generico y daba 500 donde toca 404."""
    repo["find_by_id"].return_value = None

    with pytest.raises(ResourceNotFoundException):
        await UserService.actualizar_usuario(sesion, user_id=999, permiso="ADMIN")

    sesion.commit.assert_not_awaited()


# -------------------------------------------------------------------------
# delete_user_by_id: borrado LOGICO
# -------------------------------------------------------------------------
async def test_borrar_un_usuario_solo_lo_deshabilita(sesion, repo):
    """DESVIACION DELIBERADA respecto al Java, que hace un DELETE de verdad.
    No se puede: users tiene dos FK con ON DELETE CASCADE
    (authorities.username y ventas.id_username, comprobado en Aiven), asi que
    el DELETE real se llevaria TODO el historial de ventas del usuario sin
    avisar."""
    usuario = construir_usuario(id=7, enabled=True)
    repo["find_by_id"].return_value = usuario

    await UserService.delete_user_by_id(sesion, 7)

    assert usuario.enabled is False
    # Lo que NO debe pasar: ningun DELETE.
    repo["delete"].assert_not_awaited()
    sesion.commit.assert_awaited_once()


async def test_borrar_un_usuario_inexistente_lanza_el_404(sesion, repo):
    repo["find_by_id"].return_value = None

    with pytest.raises(ResourceNotFoundException):
        await UserService.delete_user_by_id(sesion, 999)

    sesion.commit.assert_not_awaited()
