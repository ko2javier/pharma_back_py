# tests/test_user_controller.py
#
# NIVEL 2: los 5 endpoints de /users, con el peso en las reglas de rol.
#
# Estas reglas son el sitio donde mas facil es que un fallo ABRA en vez de
# cerrar, y sin hacer ruido. Ya paso una vez: el controlador leia el rol con
# payload.get("rol") cuando el claim se llama "role", asi que devolvia ""
# siempre y las tres reglas finas no se disparaban JAMAS. Nadie se entera de
# un 403 que no sucede. Por eso cada regla tiene aqui su test con el rol que
# SI debe pasar y el que NO.
#
# ENDURECIMIENTO DELIBERADO respecto al Java: un SELLER recibe 403 en los tres
# endpoints que escriben. En el Java, un SELLER con token puede crearse un
# SUPERADMIN (UserController solo mira "ADMIN".equals), y la restriccion vive
# solo en el Angular (home.component.html:57 esconde el boton). Esconder el
# boton no es proteger el endpoint.
from unittest.mock import AsyncMock

import pytest

from app.exceptions.custom import DuplicateResourceException
from app.services.user_service import UserService
from tests.conftest import construir_usuario


@pytest.fixture
def servicio(monkeypatch):
    espias = {}
    for nombre in (
        "get_all_users",
        "get_user_by_username",
        "get_user_by_id",
        "crear_usuario",
        "actualizar_usuario",
        "delete_user_by_id",
    ):
        espia = AsyncMock()
        monkeypatch.setattr(UserService, nombre, espia)
        espias[nombre] = espia
    return espias


# -------------------------------------------------------------------------
# GET /users/all  y  GET /users/{username}
# -------------------------------------------------------------------------
async def test_listar_usuarios_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["get_all_users"].return_value = [construir_usuario(username="ko2")]

    r = await client.get("/users/all")

    assert r.status_code == 200
    assert r.json()[0]["username"] == "ko2"


async def test_la_respuesta_nunca_incluye_la_password(client, autenticar, servicio):
    """UserOut no declara el campo. Es el @JsonProperty(access = WRITE_ONLY)
    del Java: la password entra en las peticiones y no sale jamas."""
    autenticar()
    servicio["get_all_users"].return_value = [construir_usuario()]

    r = await client.get("/users/all")

    assert set(r.json()[0]) == {"id", "username", "enabled", "permiso"}
    assert "password" not in r.text


async def test_lista_vacia_da_204(client, autenticar, servicio):
    autenticar()
    servicio["get_all_users"].return_value = []

    r = await client.get("/users/all")

    assert r.status_code == 204


async def test_users_all_no_se_lo_come_la_ruta_username(client, autenticar, servicio):
    """La trampa de orden de rutas: FastAPI resuelve por orden de declaracion,
    asi que /users/all tiene que ir ANTES de /users/{username} o "all" se
    interpreta como un nombre de usuario. En Spring no pasaba: elegia la ruta
    literal.

    No se comprueba leyendo el codigo sino viendo a que funcion del service
    llega la peticion."""
    autenticar()
    servicio["get_all_users"].return_value = [construir_usuario()]

    await client.get("/users/all")

    servicio["get_all_users"].assert_awaited_once()
    servicio["get_user_by_username"].assert_not_awaited()


async def test_buscar_por_username_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["get_user_by_username"].return_value = construir_usuario(username="ko2")

    r = await client.get("/users/ko2")

    assert r.status_code == 200
    assert r.json()["username"] == "ko2"


async def test_username_inexistente_da_404(client, autenticar, servicio):
    autenticar()
    servicio["get_user_by_username"].return_value = None

    r = await client.get("/users/fulano")

    assert r.status_code == 404
    assert r.json() == {"error": "Usuario no encontrado: fulano"}


# -------------------------------------------------------------------------
# POST /users/insert
# -------------------------------------------------------------------------
async def test_crear_usuario_devuelve_201(client, autenticar, servicio):
    """201, al contrario que POST /articulos/insert, que da 200. No es una
    incoherencia del espejo: es asi en el Java y se replica."""
    autenticar(permiso="SUPERADMIN")
    servicio["crear_usuario"].return_value = construir_usuario(username="nuevo", permiso="ADMIN")

    r = await client.post(
        "/users/insert",
        json={"username": "nuevo", "password": "Pass1234!", "permiso": "ADMIN"},
    )

    assert r.status_code == 201


async def test_crear_usuario_registra_INSERT_USER(client, autenticar, servicio, log):
    autenticar(username="jefe", permiso="SUPERADMIN")
    servicio["crear_usuario"].return_value = construir_usuario(username="nuevo")

    await client.post(
        "/users/insert",
        json={"username": "nuevo", "password": "Pass1234!", "permiso": "SELLER"},
    )

    args = log.await_args.args
    assert args[1] == "jefe"
    assert args[2] == "INSERT_USER"
    assert args[3] == "nuevo"


async def test_username_duplicado_da_409(client, autenticar, servicio):
    """El chequeo vive en el service, no en el controlador: asi no se puede
    saltar llamando al service desde otro sitio. Sin el, el INSERT moriria con
    el error de clave unica de MySQL -> 500 donde el Java da 409."""
    autenticar(permiso="SUPERADMIN")
    servicio["crear_usuario"].side_effect = DuplicateResourceException("El usuario ya existe: ko2")

    r = await client.post(
        "/users/insert",
        json={"username": "ko2", "password": "x", "permiso": "SELLER"},
    )

    assert r.status_code == 409
    assert r.json() == {"error": "El usuario ya existe: ko2"}


async def test_un_ADMIN_no_puede_crear_otro_ADMIN(client, autenticar, servicio, log):
    autenticar(username="admin1", permiso="ADMIN")

    r = await client.post(
        "/users/insert",
        json={"username": "nuevo", "password": "x", "permiso": "ADMIN"},
    )

    assert r.status_code == 403
    assert r.json()["detail"] == "Un ADMIN solo puede crear usuarios con rol SELLER"
    # Y nunca se llego al service: el alta no ocurrio.
    servicio["crear_usuario"].assert_not_awaited()
    # El intento queda registrado: es el rastro de seguridad que interesa.
    args = log.await_args.args
    assert args[2] == "FORBIDDEN_ACTION"


async def test_un_ADMIN_si_puede_crear_un_SELLER(client, autenticar, servicio):
    # El control negativo del test de arriba: la regla no puede ser "ADMIN no
    # crea nada".
    autenticar(permiso="ADMIN")
    servicio["crear_usuario"].return_value = construir_usuario(username="vendedor", permiso="SELLER")

    r = await client.post(
        "/users/insert",
        json={"username": "vendedor", "password": "x", "permiso": "SELLER"},
    )

    assert r.status_code == 201


async def test_un_SELLER_no_puede_crear_usuarios(client, autenticar, servicio, log):
    # ENDURECIMIENTO: en el Java esto devuelve 201 y el SELLER se fabrica un
    # SUPERADMIN.
    autenticar(username="vendedor", permiso="SELLER")

    r = await client.post(
        "/users/insert",
        json={"username": "yo_mismo", "password": "x", "permiso": "SUPERADMIN"},
    )

    assert r.status_code == 403
    assert r.json()["detail"] == "Un SELLER no puede gestionar usuarios"
    servicio["crear_usuario"].assert_not_awaited()
    args = log.await_args.args
    assert args[2] == "FORBIDDEN_ACTION"
    assert args[3] == "Intento de crear usuario siendo SELLER"


# -------------------------------------------------------------------------
# PUT /users/update
# -------------------------------------------------------------------------
async def test_actualizar_usuario_devuelve_200(client, autenticar, servicio):
    autenticar(permiso="SUPERADMIN")
    servicio["get_user_by_id"].return_value = construir_usuario(id=7, permiso="SELLER")
    servicio["actualizar_usuario"].return_value = construir_usuario(id=7, permiso="ADMIN")

    r = await client.put("/users/update", json={"id": 7, "permiso": "ADMIN"})

    assert r.status_code == 200
    assert r.json()["permiso"] == "ADMIN"


async def test_actualizar_un_usuario_inexistente_da_404(client, autenticar, servicio):
    autenticar(permiso="SUPERADMIN")
    servicio["get_user_by_id"].return_value = None

    r = await client.put("/users/update", json={"id": 999, "permiso": "ADMIN"})

    assert r.status_code == 404
    servicio["actualizar_usuario"].assert_not_awaited()


@pytest.mark.parametrize("permiso_objetivo", ["ADMIN", "SUPERADMIN"])
async def test_un_ADMIN_no_modifica_a_otro_ADMIN_ni_a_un_SUPERADMIN(
    client, autenticar, servicio, log, permiso_objetivo
):
    """La regla depende del rol del usuario OBJETIVO, no del que llama: por eso
    no puede vivir en router.py como un require_role."""
    autenticar(username="admin1", permiso="ADMIN")
    servicio["get_user_by_id"].return_value = construir_usuario(
        id=7, username="otro", permiso=permiso_objetivo
    )

    r = await client.put("/users/update", json={"id": 7, "permiso": "SELLER"})

    assert r.status_code == 403
    servicio["actualizar_usuario"].assert_not_awaited()
    assert log.await_args.args[2] == "FORBIDDEN_ACTION"


async def test_un_ADMIN_si_modifica_a_un_SELLER(client, autenticar, servicio):
    autenticar(permiso="ADMIN")
    servicio["get_user_by_id"].return_value = construir_usuario(id=7, permiso="SELLER")
    servicio["actualizar_usuario"].return_value = construir_usuario(id=7, permiso="SELLER")

    r = await client.put("/users/update", json={"id": 7, "permiso": "SELLER"})

    assert r.status_code == 200


async def test_un_SELLER_no_puede_modificar_usuarios(client, autenticar, servicio, log):
    autenticar(username="vendedor", permiso="SELLER")

    r = await client.put("/users/update", json={"id": 1, "permiso": "SUPERADMIN"})

    assert r.status_code == 403
    # Corta ANTES de buscar al objetivo: ni siquiera se consulta la BD.
    servicio["get_user_by_id"].assert_not_awaited()
    assert log.await_args.args[3] == "Intento de modificar usuario siendo SELLER"


async def test_la_password_es_opcional_al_actualizar(client, autenticar, servicio):
    """Si no viene, se conserva la que tenia. Si el schema la exigiera, cada
    cambio de rol obligaria a reescribir la contrasena del usuario."""
    autenticar(permiso="SUPERADMIN")
    servicio["get_user_by_id"].return_value = construir_usuario(id=7, permiso="SELLER")
    servicio["actualizar_usuario"].return_value = construir_usuario(id=7)

    await client.put("/users/update", json={"id": 7, "permiso": "ADMIN"})

    assert servicio["actualizar_usuario"].await_args.kwargs["raw_password"] is None


# -------------------------------------------------------------------------
# DELETE /users/{id}
# -------------------------------------------------------------------------
async def test_borrar_usuario_devuelve_204(client, autenticar, servicio):
    autenticar(permiso="SUPERADMIN")
    servicio["get_user_by_id"].return_value = construir_usuario(id=7, username="victima", permiso="SELLER")

    r = await client.delete("/users/7")

    assert r.status_code == 204
    assert r.content == b""


async def test_borrar_usuario_registra_DELETE_USER_con_el_nombre_del_objetivo(
    client, autenticar, servicio, log
):
    autenticar(username="jefe", permiso="SUPERADMIN")
    servicio["get_user_by_id"].return_value = construir_usuario(id=7, username="victima", permiso="SELLER")

    await client.delete("/users/7")

    args = log.await_args.args
    assert args[1] == "jefe"        # quien lo hizo
    assert args[2] == "DELETE_USER"
    assert args[3] == "victima"     # a quien


async def test_borrar_un_usuario_inexistente_da_404(client, autenticar, servicio):
    autenticar(permiso="SUPERADMIN")
    servicio["get_user_by_id"].return_value = None

    r = await client.delete("/users/999")

    assert r.status_code == 404
    servicio["delete_user_by_id"].assert_not_awaited()


@pytest.mark.parametrize("permiso_objetivo", ["ADMIN", "SUPERADMIN"])
async def test_un_ADMIN_no_borra_a_otro_ADMIN_ni_a_un_SUPERADMIN(
    client, autenticar, servicio, log, permiso_objetivo
):
    autenticar(permiso="ADMIN")
    servicio["get_user_by_id"].return_value = construir_usuario(id=7, permiso=permiso_objetivo)

    r = await client.delete("/users/7")

    assert r.status_code == 403
    servicio["delete_user_by_id"].assert_not_awaited()
    assert log.await_args.args[2] == "FORBIDDEN_ACTION"


async def test_un_SELLER_no_puede_borrar_usuarios(client, autenticar, servicio, log):
    autenticar(permiso="SELLER")

    r = await client.delete("/users/1")

    assert r.status_code == 403
    servicio["get_user_by_id"].assert_not_awaited()
    assert log.await_args.args[3] == "Intento de DELETE de usuario siendo SELLER"
