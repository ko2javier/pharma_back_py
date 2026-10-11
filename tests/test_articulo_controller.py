# tests/test_articulo_controller.py
#
# NIVEL 2: los 7 endpoints de /articulos con el service sustituido.
#
# Lo que se vigila aqui, por orden de importancia:
#   1. El 204 con lista vacia (lo hace el Java: ArticuloController.java:44-50)
#      y el 404 del updateStock vacio, que NO es lo mismo.
#   2. Que las excepciones del paso 8 salgan con su codigo y NO como 500: ese
#      era el estado anterior, donde "no encontrado" y "stock insuficiente"
#      iban en el mismo RuntimeException.
#   3. La clave camelCase "aempsCode" del JSON, que es la que lee el Angular.
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm.exc import StaleDataError

from app.exceptions.custom import (
    InsufficientStockException,
    ResourceNotFoundException,
)
from app.services.articulo_service import ArticuloService
from tests.conftest import construir_articulo


@pytest.fixture
def servicio(monkeypatch):
    """Sustituye los metodos de ArticuloService que usan los endpoints.

    Se parchea el metodo en la CLASE, no en el modulo del controlador: el
    controlador importo la misma clase, asi que ve el parche. Si se parcheara
    "app.api.routes.articulo_controller.ArticuloService" tambien valdria, pero
    habria que repetirlo en cada fichero que lo use.
    """
    espias = {}
    for nombre in (
        "get_all",
        "search_by_keyword",
        "update_stock_batch",
        "update_item",
        "insertar_articulo",
        "get_by_id",
        "delete_articulo_by_id",
        "link_aemps",
    ):
        espia = AsyncMock()
        monkeypatch.setattr(ArticuloService, nombre, espia)
        espias[nombre] = espia
    return espias


# -------------------------------------------------------------------------
# GET /articulos/All  y  GET /articulos/search/{keyword}
# -------------------------------------------------------------------------
async def test_listar_todos_devuelve_200_con_la_lista(client, autenticar, servicio):
    autenticar()
    servicio["get_all"].return_value = [construir_articulo()]

    r = await client.get("/articulos/All")

    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["nombre"] == "Ibuprofeno 600mg"


async def test_listar_todos_devuelve_la_clave_aempsCode_en_camelCase(client, autenticar, servicio):
    """El alias de Pydantic sale porque FastAPI serializa con by_alias=True.
    En Python el campo es aemps_code; el Angular espera aempsCode."""
    autenticar()
    servicio["get_all"].return_value = [construir_articulo(aemps_code="67031")]

    r = await client.get("/articulos/All")

    assert "aempsCode" in r.json()[0]
    assert "aemps_code" not in r.json()[0]
    assert r.json()[0]["aempsCode"] == "67031"


async def test_listar_todos_con_inventario_vacio_da_204_sin_cuerpo(client, autenticar, servicio):
    # Replica de ArticuloController.java:44-50 (noContent). OJO: esto NO se
    # copia en /activity-log ni en /cancelaciones, que devuelven 200 [].
    autenticar()
    servicio["get_all"].return_value = []

    r = await client.get("/articulos/All")

    assert r.status_code == 204
    assert r.content == b""


async def test_buscar_por_palabra_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["search_by_keyword"].return_value = [construir_articulo()]

    r = await client.get("/articulos/search/ibupro")

    assert r.status_code == 200
    servicio["search_by_keyword"].assert_awaited_once()
    # El keyword llega tal cual al service, sin tocar.
    assert servicio["search_by_keyword"].await_args.args[1] == "ibupro"


async def test_buscar_sin_resultados_da_204(client, autenticar, servicio):
    autenticar()
    servicio["search_by_keyword"].return_value = []

    r = await client.get("/articulos/search/noexiste")

    assert r.status_code == 204


# -------------------------------------------------------------------------
# PUT /articulos/updateStock  (el del carrito)
# -------------------------------------------------------------------------
async def test_actualizar_stock_devuelve_los_articulos_actualizados(client, autenticar, servicio):
    autenticar()
    servicio["update_stock_batch"].return_value = [construir_articulo(cantidad=48)]

    r = await client.put(
        "/articulos/updateStock",
        json=[{"codigo": "8470001234567", "cantidadVendida": 2}],
    )

    assert r.status_code == 200
    assert r.json()[0]["cantidad"] == 48


async def test_actualizar_stock_con_lista_vacia_da_404(client, autenticar, servicio):
    """Este 404 no es "el articulo no existe": es que llego una lista vacia y
    no se actualizo nada. El Java responde igual (notFound cuando la lista
    vuelve vacia, ArticuloController.java:56-58)."""
    autenticar()
    servicio["update_stock_batch"].return_value = []

    r = await client.put("/articulos/updateStock", json=[])

    assert r.status_code == 404
    assert r.json()["detail"] == "No se actualizaron artículos"


async def test_articulo_inexistente_en_el_lote_da_404_y_no_500(client, autenticar, servicio):
    # Antes del paso 8 esto era un ValueError sin handler: 500.
    autenticar()
    servicio["update_stock_batch"].side_effect = ResourceNotFoundException(
        "Artículo no encontrado: 8470009999999"
    )

    r = await client.put(
        "/articulos/updateStock",
        json=[{"codigo": "8470009999999", "cantidadVendida": 1}],
    )

    assert r.status_code == 404
    # La clave es "error", la del GlobalExceptionHandler del Java, no "detail".
    assert r.json() == {"error": "Artículo no encontrado: 8470009999999"}


async def test_stock_insuficiente_da_409_y_no_404(client, autenticar, servicio):
    """En el Java los dos motivos iban en el mismo RuntimeException y los dos
    acababan en 500, asi que el frontend no podia distinguirlos. Aqui el 409
    tiene mensaje propio en carritocomponent.ts:189."""
    autenticar()
    servicio["update_stock_batch"].side_effect = InsufficientStockException(
        "Stock insuficiente para 8470001234567"
    )

    r = await client.put(
        "/articulos/updateStock",
        json=[{"codigo": "8470001234567", "cantidadVendida": 999}],
    )

    assert r.status_code == 409
    assert r.json() == {"error": "Stock insuficiente para 8470001234567"}


async def test_el_bloqueo_optimista_da_409_con_mensaje_para_el_usuario(client, autenticar, servicio):
    """StaleDataError es el OptimisticLockException de Hibernate: otra caja
    toco el mismo articulo entre el SELECT y el UPDATE. El mensaje lo pone el
    handler, no el service, porque el del service no es presentable."""
    autenticar()
    servicio["update_stock_batch"].side_effect = StaleDataError("version mismatch")

    r = await client.put(
        "/articulos/updateStock",
        json=[{"codigo": "8470001234567", "cantidadVendida": 1}],
    )

    assert r.status_code == 409
    assert "otro usuario" in r.json()["error"]


# -------------------------------------------------------------------------
# PUT /articulos/updateItem
# -------------------------------------------------------------------------
async def test_actualizar_articulo_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["update_item"].return_value = construir_articulo(precio=9.99)

    r = await client.put(
        "/articulos/updateItem",
        json={"codigo": "8470001234567", "cantidad": 10, "precio": 9.99},
    )

    assert r.status_code == 200
    assert r.json()["precio"] == 9.99


async def test_actualizar_articulo_inexistente_da_404(client, autenticar, servicio):
    autenticar()
    servicio["update_item"].side_effect = ResourceNotFoundException("Artículo no encontrado: X")

    r = await client.put("/articulos/updateItem", json={"codigo": "X"})

    assert r.status_code == 404


# -------------------------------------------------------------------------
# POST /articulos/insert
# -------------------------------------------------------------------------
async def test_insertar_devuelve_200_y_NO_201(client, autenticar, servicio):
    """Contraste con POST /users/insert, que si da 201. El estilo de cada
    endpoint se lee en su Java, no en el endpoint de al lado."""
    autenticar()
    servicio["insertar_articulo"].return_value = construir_articulo()

    r = await client.post(
        "/articulos/insert",
        json={"nombre": "Ibuprofeno 600mg", "categoria": "Antiinflamatorio",
              "precio": 12.95, "cantidad": 50},
    )

    assert r.status_code == 200


async def test_insertar_registra_INSERT_PRODUCT_con_el_usuario_del_token(client, autenticar, servicio, log):
    autenticar(username="farmaceutico01")
    servicio["insertar_articulo"].return_value = construir_articulo(nombre="Nolotil")

    await client.post(
        "/articulos/insert",
        json={"nombre": "Nolotil", "categoria": "Analgésico", "precio": 5.0, "cantidad": 10},
    )

    # Aqui el log se llama con argumentos POSICIONALES (en auth_controller van
    # con nombre). Orden: session, username, action, detail, ip.
    args = log.await_args.args
    assert args[1] == "farmaceutico01"
    assert args[2] == "INSERT_PRODUCT"
    assert args[3] == "Nolotil"


async def test_el_codigo_no_se_acepta_del_cliente(client, autenticar, servicio):
    """ArticuloCreate no declara 'codigo': lo genera el service. Si se cuela en
    el JSON, Pydantic lo ignora en vez de aceptarlo."""
    autenticar()
    servicio["insertar_articulo"].return_value = construir_articulo()

    await client.post(
        "/articulos/insert",
        json={"nombre": "X", "categoria": "Y", "precio": 1.0, "cantidad": 1,
              "codigo": "0000000000000"},
    )

    dto = servicio["insertar_articulo"].await_args.args[1]
    assert not hasattr(dto, "codigo")


# -------------------------------------------------------------------------
# DELETE /articulos/{id}
# -------------------------------------------------------------------------
async def test_borrar_devuelve_204_sin_cuerpo(client, autenticar, servicio):
    autenticar()
    servicio["get_by_id"].return_value = construir_articulo(nombre="Nolotil")
    servicio["delete_articulo_by_id"].return_value = None

    r = await client.delete("/articulos/1")

    assert r.status_code == 204
    assert r.content == b""


async def test_borrar_registra_el_NOMBRE_del_articulo_no_el_id(client, autenticar, servicio, log):
    """Por eso el controlador hace un get_by_id antes de borrar: despues del
    DELETE ya no hay forma de saber como se llamaba, y un log que dice
    "id=37" no sirve de nada dentro de seis meses."""
    autenticar()
    servicio["get_by_id"].return_value = construir_articulo(nombre="Nolotil")

    await client.delete("/articulos/1")

    args = log.await_args.args
    assert args[2] == "DELETE_PRODUCT"
    assert args[3] == "Nolotil"


async def test_borrar_un_articulo_inexistente_da_404(client, autenticar, servicio):
    autenticar()
    servicio["get_by_id"].return_value = None
    servicio["delete_articulo_by_id"].side_effect = ResourceNotFoundException(
        "Artículo no encontrado con id: 999"
    )

    r = await client.delete("/articulos/999")

    assert r.status_code == 404


async def test_si_el_borrado_falla_no_se_registra_nada(client, autenticar, servicio, log):
    # El log va DESPUES del delete y sin try: si el delete revienta, no queda
    # rastro de un borrado que no ocurrio. Es lo correcto aqui.
    autenticar()
    servicio["get_by_id"].return_value = None
    servicio["delete_articulo_by_id"].side_effect = ResourceNotFoundException("no existe")

    await client.delete("/articulos/999")

    log.assert_not_awaited()


# -------------------------------------------------------------------------
# PATCH /articulos/{id}/aemps
# -------------------------------------------------------------------------
async def test_vincular_aemps_devuelve_200(client, autenticar, servicio):
    autenticar()
    servicio["link_aemps"].return_value = construir_articulo(aemps_code="67031")

    r = await client.patch(
        "/articulos/1/aemps",
        json={"aempsCode": "67031", "laboratorio": "Kern Pharma"},
    )

    assert r.status_code == 200
    assert r.json()["aempsCode"] == "67031"


async def test_vincular_aemps_acepta_la_clave_en_camelCase(client, autenticar, servicio):
    """populate_by_name=True hace que entren las dos formas, pero la que manda
    el Angular es aempsCode: si se rompiera el alias, el codigo llegaria como
    None y el articulo se quedaria sin vincular, en silencio y con un 200."""
    autenticar()
    servicio["link_aemps"].return_value = construir_articulo()

    await client.patch("/articulos/1/aemps", json={"aempsCode": "67031", "laboratorio": "Kern"})

    # link_aemps(session, id, aemps_code, laboratorio)
    args = servicio["link_aemps"].await_args.args
    assert args[2] == "67031"
    assert args[3] == "Kern"


async def test_vincular_aemps_en_articulo_inexistente_da_404(client, autenticar, servicio):
    autenticar()
    servicio["link_aemps"].side_effect = ResourceNotFoundException("Artículo no encontrado con id: 999")

    r = await client.patch("/articulos/999/aemps", json={"aempsCode": "1"})

    assert r.status_code == 404
