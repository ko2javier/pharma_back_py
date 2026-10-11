# tests/test_venta_controller.py
#
# NIVEL 2: los 5 endpoints de /ventas.
#
# El valor de este fichero esta en los codigos, que son un muestrario de
# incoherencias del Java que hay que replicar tal cual:
#
#   GET  /ventas/all          lista vacia -> 204   (pero /cancelaciones da 200 [])
#   POST /ventas/registrar    exito       -> 200   (pero /users/insert da 201)
#   DELETE /ventas/cancelar/1 exito       -> 200 con cuerpo vacio (no 204)
#
# Y dos cosas que no son codigos:
#   * Registrar una venta NO descuenta stock. El Java inyecta el repositorio
#     de articulos en VentaService y no lo usa; el descuento lo hace el
#     frontend en una segunda peticion (carritocomponent.ts:157 ->
#     PUT /articulos/updateStock). Si esa segunda falla, la venta queda
#     registrada y el stock sin tocar. Es deuda real de produccion y se
#     replica; aqui solo se deja constancia.
#   * El 'responsable' de la cancelacion llega por query param y el Java no lo
#     valida: se puede firmar con el nombre de otro. Por eso el CANCEL_SALE
#     guarda el username DEL TOKEN, que es otra cosa distinta a proposito.
from unittest.mock import AsyncMock

import pytest

from app.exceptions.custom import ResourceNotFoundException
from app.services.venta_service import VentaService
from tests.conftest import construir_venta


@pytest.fixture
def servicio(monkeypatch):
    espias = {}
    for nombre in ("get_all", "get_all_by_username", "registrar_venta",
                   "registrar_ventas", "cancelar_venta"):
        espia = AsyncMock()
        monkeypatch.setattr(VentaService, nombre, espia)
        espias[nombre] = espia
    return espias


VENTA_JSON = {
    "dnicliente": "12345678A",
    "nameproducto": "Ibuprofeno 600mg",
    "cantidad": 2,
    "importe": 25.90,
    "codigo": "8470001234567",
}


# -------------------------------------------------------------------------
# GET /ventas/all  y  GET /ventas/{username}
# -------------------------------------------------------------------------
async def test_listar_todas_las_ventas_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["get_all"].return_value = [construir_venta()]

    r = await client.get("/ventas/all")

    assert r.status_code == 200
    assert r.json()[0]["dnicliente"] == "12345678A"


async def test_el_json_dice_username_aunque_la_columna_se_llame_id_username(
    client, autenticar, servicio
):
    """La columna de MySQL es id_username; el atributo Python es username, y el
    JSON que siempre vio el frontend es "username" (Jackson serializaba el
    campo Java, no la columna). Si esto cambiara, el historial de ventas del
    Angular se quedaria en blanco."""
    autenticar()
    servicio["get_all"].return_value = [construir_venta(username="ko2")]

    r = await client.get("/ventas/all")

    assert r.json()[0]["username"] == "ko2"
    assert "id_username" not in r.json()[0]


async def test_sin_ventas_da_204_sin_cuerpo(client, autenticar, servicio):
    autenticar()
    servicio["get_all"].return_value = []

    r = await client.get("/ventas/all")

    assert r.status_code == 204
    assert r.content == b""


async def test_ventas_all_no_se_lo_come_la_ruta_username(client, autenticar, servicio):
    """Tercera aparicion de la colision de rutas en el proyecto (antes paso con
    /users/all y con /articulos). Se comprueba viendo a que funcion del
    service llega la peticion, no leyendo el orden en el fichero."""
    autenticar()
    servicio["get_all"].return_value = [construir_venta()]

    await client.get("/ventas/all")

    servicio["get_all"].assert_awaited_once()
    servicio["get_all_by_username"].assert_not_awaited()


async def test_ventas_de_un_usuario_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["get_all_by_username"].return_value = [construir_venta(username="ko2")]

    r = await client.get("/ventas/ko2")

    assert r.status_code == 200
    assert servicio["get_all_by_username"].await_args.args[1] == "ko2"


async def test_usuario_sin_ventas_da_204(client, autenticar, servicio):
    autenticar()
    servicio["get_all_by_username"].return_value = []

    r = await client.get("/ventas/fulano")

    assert r.status_code == 204


# -------------------------------------------------------------------------
# POST /ventas/registrar  y  POST /ventas/registrar/list
# -------------------------------------------------------------------------
async def test_registrar_una_venta_devuelve_200_y_no_201(client, autenticar, servicio):
    autenticar()
    servicio["registrar_venta"].return_value = construir_venta()

    r = await client.post("/ventas/registrar", json=VENTA_JSON)

    assert r.status_code == 200


async def test_el_vendedor_sale_del_token_y_no_del_cuerpo(client, autenticar, servicio):
    """VentaCreate no declara username, fecha ni hora: los pone el servidor. Si
    el cliente pudiera elegirlos, cualquiera firmaria ventas a nombre de otro
    con un curl."""
    autenticar(username="vendedor7")
    servicio["registrar_venta"].return_value = construir_venta()

    await client.post("/ventas/registrar", json={**VENTA_JSON, "username": "otro"})

    # registrar_venta(session, username, venta_dto)
    assert servicio["registrar_venta"].await_args.args[1] == "vendedor7"


async def test_registrar_una_lista_devuelve_200_con_todas(client, autenticar, servicio):
    """Este es el que usa el carrito de verdad; el singular esta muerto."""
    autenticar()
    servicio["registrar_ventas"].return_value = [construir_venta(id=1), construir_venta(id=2)]

    r = await client.post("/ventas/registrar/list", json=[VENTA_JSON, VENTA_JSON])

    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_registrar_no_toca_el_stock(client, autenticar, servicio):
    """Deja constancia de la deuda: el endpoint de ventas no llama a nada de
    articulos. El descuento lo hace el frontend en una segunda peticion, sin
    transaccion comun. Si algun dia alguien "arregla" esto, este test se cae y
    obliga a mirar si el Angular dejo de mandar su PUT /updateStock, que
    entonces descontaria dos veces."""
    autenticar()
    servicio["registrar_venta"].return_value = construir_venta()

    await client.post("/ventas/registrar", json=VENTA_JSON)

    # Solo se llamo al service de ventas, a ningun otro.
    servicio["registrar_venta"].assert_awaited_once()


# -------------------------------------------------------------------------
# DELETE /ventas/cancelar/{id}
# -------------------------------------------------------------------------
async def test_cancelar_devuelve_200_con_cuerpo_vacio(client, autenticar, servicio):
    # 200 y no 204: el Java devuelve ResponseEntity<Void> con ok().
    autenticar()
    servicio["cancelar_venta"].return_value = None

    r = await client.delete("/ventas/cancelar/1?responsable=admin")

    assert r.status_code == 200
    assert r.content == b""


async def test_cancelar_sin_el_parametro_responsable_da_422(client, autenticar, servicio):
    """'responsable' es obligatorio: no tiene valor por defecto en la firma del
    endpoint, asi que FastAPI lo exige como query param."""
    autenticar()

    r = await client.delete("/ventas/cancelar/1")

    assert r.status_code == 422
    servicio["cancelar_venta"].assert_not_awaited()


async def test_cancelar_una_venta_inexistente_da_404_y_no_500(client, autenticar, servicio):
    """Antes el service lanzaba un ValueError con el comentario "mas adelante
    el controlador atrapara esto". No lo atrapaba nadie: 500."""
    autenticar()
    servicio["cancelar_venta"].side_effect = ResourceNotFoundException(
        "Venta no encontrada con id: 999"
    )

    r = await client.delete("/ventas/cancelar/999?responsable=admin")

    assert r.status_code == 404
    assert r.json() == {"error": "Venta no encontrada con id: 999"}


async def test_el_log_guarda_quien_lo_pidio_no_quien_firma(client, autenticar, servicio, log):
    """Son dos cosas distintas a proposito. El 'responsable' lo elige el
    cliente y el Java no lo valida (se puede firmar con el nombre de otro); el
    CANCEL_SALE guarda el username del TOKEN, que no se puede falsificar."""
    autenticar(username="vendedor7")
    servicio["cancelar_venta"].return_value = None

    await client.delete("/ventas/cancelar/42?responsable=el_jefe")

    args = log.await_args.args
    assert args[1] == "vendedor7"      # del token
    assert args[2] == "CANCEL_SALE"
    assert args[3] == "id=42"
    # Y el que firma la cancelacion en la tabla es el otro:
    assert servicio["cancelar_venta"].await_args.args[2] == "el_jefe"


async def test_si_la_cancelacion_falla_no_se_registra_nada(client, autenticar, servicio, log):
    autenticar()
    servicio["cancelar_venta"].side_effect = ResourceNotFoundException("no existe")

    await client.delete("/ventas/cancelar/999?responsable=admin")

    log.assert_not_awaited()
