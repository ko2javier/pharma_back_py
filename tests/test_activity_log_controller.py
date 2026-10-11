# tests/test_activity_log_controller.py
#
# NIVEL 2: el unico endpoint de /activity-log, y el unico de los 25 que no es
# "autenticado a secas" — pide SUPERADMIN (SecurityConfig.java:64).
#
# Es el primer y unico uso de require_role en el proyecto, asi que estos tests
# prueban tambien la propia fabrica de dependencias de deps.py. Dos detalles
# que no son evidentes y que aqui quedan fijados:
#
#   1. El rol se compara SIN el prefijo ROLE_. Spring lo antepone solo en
#      hasRole(); aqui se compara contra Users.permiso crudo. Con
#      "ROLE_SUPERADMIN" no entraria nadie, y sin hacer ruido.
#   2. require_role ya depende de get_current_user por dentro, asi que el
#      override de la fixture 'autenticar' lo cubre tambien.
from unittest.mock import AsyncMock

import pytest

from app.services.activity_log_service import ActivityLogService
from tests.conftest import construir_log


@pytest.fixture
def listado(monkeypatch):
    # OJO: aqui se parchea get_all, no log. La fixture 'log' del conftest ya
    # sustituye la escritura en todos los tests; esta es la lectura.
    espia = AsyncMock()
    monkeypatch.setattr(ActivityLogService, "get_all", espia)
    return espia


async def test_sin_token_da_401(client, listado):
    r = await client.get("/activity-log/all")
    assert r.status_code == 401
    listado.assert_not_awaited()


@pytest.mark.parametrize("permiso", ["ADMIN", "SELLER"])
async def test_un_rol_que_no_es_SUPERADMIN_recibe_403(client, autenticar, listado, permiso):
    """403 y no 401: el token es valido, lo que falta es el permiso. Que un
    ADMIN tenga 403 aqui es lo que diferencia este endpoint de los otros 23."""
    autenticar(permiso=permiso)

    r = await client.get("/activity-log/all")

    assert r.status_code == 403
    assert r.json()["detail"] == "No tienes permiso para acceder a este recurso"
    # Y no se llego a consultar nada: el corte es antes del endpoint.
    listado.assert_not_awaited()


async def test_un_SUPERADMIN_entra(client, autenticar, listado):
    autenticar(permiso="SUPERADMIN")
    listado.return_value = [construir_log()]

    r = await client.get("/activity-log/all")

    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_el_rol_se_compara_sin_el_prefijo_ROLE_(client, autenticar, listado):
    """Control negativo del test de arriba: si deps.py comparara contra
    "ROLE_SUPERADMIN", el usuario de la BD (que tiene "SUPERADMIN" crudo) se
    quedaria fuera. Y al reves: un permiso que YA trajera el prefijo no debe
    colarse."""
    autenticar(permiso="ROLE_SUPERADMIN")

    r = await client.get("/activity-log/all")

    assert r.status_code == 403


async def test_lista_vacia_da_200_y_no_204(client, autenticar, listado):
    """El 204 de /articulos NO se copia aqui: ArticuloController.java:44-50
    hace noContent(), ActivityLogController.java:19 devuelve la List pelada.
    Comprobado en el Java antes de escribirlo."""
    autenticar(permiso="SUPERADMIN")
    listado.return_value = []

    r = await client.get("/activity-log/all")

    assert r.status_code == 200
    assert r.json() == []


async def test_la_ip_sale_como_ipAddress_en_camelCase(client, autenticar, listado):
    autenticar(permiso="SUPERADMIN")
    listado.return_value = [construir_log(ip_address="83.45.12.7")]

    r = await client.get("/activity-log/all")

    assert r.json()[0]["ipAddress"] == "83.45.12.7"
    assert "ip_address" not in r.json()[0]


async def test_devuelve_los_campos_del_contrato(client, autenticar, listado):
    autenticar(permiso="SUPERADMIN")
    listado.return_value = [construir_log()]

    r = await client.get("/activity-log/all")

    assert set(r.json()[0]) == {
        "id", "username", "action", "detail", "ipAddress", "fecha", "hora",
    }


async def test_el_orden_lo_decide_el_service_y_el_endpoint_no_lo_toca(
    client, autenticar, listado
):
    """El ORDER BY fecha DESC, hora DESC vive en el repositorio. El
    controlador no reordena: si lo hiciera, habria dos criterios y ganaria el
    ultimo. Se comprueba que la lista sale en el mismo orden que la devolvio
    el service."""
    autenticar(permiso="SUPERADMIN")
    listado.return_value = [
        construir_log(id=3, action="LOGIN_SUCCESS"),
        construir_log(id=2, action="INSERT_USER"),
        construir_log(id=1, action="LOGIN_FAILED"),
    ]

    r = await client.get("/activity-log/all")

    assert [fila["id"] for fila in r.json()] == [3, 2, 1]
