# tests/test_venta_cancelada_controller.py
#
# NIVEL 2: los 2 endpoints de /cancelaciones.
#
# Prefijo aparte de /ventas porque en el Java son dos @RestController
# distintos, aunque escriban la misma tabla que /ventas/cancelar.
#
# Las dos cosas que se vigilan aqui no se ven leyendo el codigo:
#   1. Devuelve 200 [] con la lista vacia, NO 204 como /ventas. Son dos
#      controladores distintos del Java y no hacen lo mismo.
#   2. La ruta es "" y no "/": con @router.get("/") la ruta real seria
#      /cancelaciones/ y el Angular, que llama sin barra, se comeria un 307
#      por peticion.
from unittest.mock import AsyncMock

import pytest

from app.services.venta_cancelada_service import VentaCanceladaService
from tests.conftest import construir_cancelacion


@pytest.fixture
def servicio(monkeypatch):
    espias = {}
    for nombre in ("obtener_todas", "registrar_cancelacion"):
        espia = AsyncMock()
        monkeypatch.setattr(VentaCanceladaService, nombre, espia)
        espias[nombre] = espia
    return espias


async def test_listar_cancelaciones_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["obtener_todas"].return_value = [construir_cancelacion()]

    r = await client.get("/cancelaciones")

    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_lista_vacia_da_200_y_un_array_vacio_no_204(client, autenticar, servicio):
    """El 204 de /ventas y /articulos NO se copia aqui. Importa: un 204 no
    trae cuerpo, y el frontend se encontraria undefined donde espera un
    array."""
    autenticar()
    servicio["obtener_todas"].return_value = []

    r = await client.get("/cancelaciones")

    assert r.status_code == 200
    assert r.json() == []


async def test_la_ruta_no_redirige_con_307(client, autenticar, servicio):
    """Trampa de FastAPI: las rutas sin segmento se declaran como "" y no como
    "/". Con "/" esto seria un 307 Temporary Redirect en CADA peticion del
    Angular."""
    autenticar()
    servicio["obtener_todas"].return_value = []

    r = await client.get("/cancelaciones")

    assert r.status_code != 307


async def test_el_json_sale_con_nombreProducto_en_camelCase(client, autenticar, servicio):
    autenticar()
    servicio["obtener_todas"].return_value = [construir_cancelacion(nombre_producto="Nolotil")]

    r = await client.get("/cancelaciones")

    assert r.json()[0]["nombreProducto"] == "Nolotil"
    assert "nombre_producto" not in r.json()[0]


async def test_registrar_una_cancelacion_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["registrar_cancelacion"].return_value = construir_cancelacion()

    r = await client.post(
        "/cancelaciones",
        json={"nombreProducto": "Nolotil", "cantidad": 2, "importe": 5.0,
              "responsable": "admin", "status": "CANCELLED"},
    )

    assert r.status_code == 200


async def test_el_id_que_mande_el_cliente_se_ignora(client, autenticar, servicio):
    """En el Java el controlador recibia la entidad VentaCancelada ENTERA, con
    su id: mandar {"id": 5} sobrescribia la fila 5. Aqui el schema de entrada
    no declara id, asi que no hay forma de que llegue — no depende de que el
    controlador se acuerde de limpiarlo."""
    autenticar()
    servicio["registrar_cancelacion"].return_value = construir_cancelacion(id=99)

    await client.post(
        "/cancelaciones",
        json={"id": 5, "nombreProducto": "Nolotil", "cantidad": 1},
    )

    dto = servicio["registrar_cancelacion"].await_args.args[1]
    assert not hasattr(dto, "id")


async def test_este_endpoint_esta_muerto_pero_se_replica(client, autenticar, servicio):
    """Ningun componente del Angular llama a POST /cancelaciones
    (registrarCancelacion existe en el service y nadie la usa). Se replica por
    contrato. El test existe para que conste que su falta de uso es conocida,
    no un olvido: si un dia alguien lo borra, que sea a sabiendas."""
    autenticar()
    servicio["registrar_cancelacion"].return_value = construir_cancelacion()

    r = await client.post("/cancelaciones", json={"cantidad": 1})

    assert r.status_code == 200
