# tests/test_articulo_service.py
#
# NIVEL 1: unitario puro. Sin HTTP y sin base de datos — se sustituye el
# REPOSITORIO y se llama al service a pelo. Es el JUnit + Mockito de siempre.
#
# Lo que hay aqui no se puede probar bien por HTTP: el comportamiento del lote
# cuando falla el tercer articulo de cinco, y el bucle del generador de
# codigos. Por HTTP solo se veria el codigo de estado.
from unittest.mock import AsyncMock

import pytest

from app.exceptions.custom import (
    InsufficientStockException,
    ResourceNotFoundException,
)
from app.repositories.articulo_repository import ArticuloRepository
from app.schemas.articulo_schema import ArticuloCreate, ArticuloUpdate
from app.services.articulo_service import ArticuloService
from tests.conftest import construir_articulo


@pytest.fixture
def repo(monkeypatch):
    espias = {}
    # codigo_en_uso va en la lista aunque parezca de mas, por lo mismo que
    # iba exists_by_id (quitado el 2026-10-18): fuera de la lista, el
    # repositorio de verdad corre contra la sesion falsa, result.scalar()
    # devuelve un mock "verdadero" y el generador cree que TODOS los codigos
    # estan ocupados -- el while True no termina y el test se cuelga, sin
    # error. delete_by_id y exists_by_id ya no existen: monkeypatch.setattr
    # falla si el atributo no existe, y tumbaria todos los tests del fichero.
    for nombre in ("find_by_codigo", "find_by_id", "codigo_en_uso", "save"):
        espia = AsyncMock()
        monkeypatch.setattr(ArticuloRepository, nombre, espia)
        espias[nombre] = espia
    # None por defecto, para TODO el fichero. Sin el, find_by_codigo devuelve
    # un mock "verdadero", y si el generador volviera a usarlo creeria
    # ocupados todos los codigos: el while True no terminaria y la bateria se
    # COLGARIA en vez de fallar (comprobado inyectando el fallo el
    # 2026-10-18: se colgaba en el primer test del generador). Los tests que
    # necesitan un articulo lo siguen poniendo con return_value.
    espias["find_by_codigo"].return_value = None
    return espias


# -------------------------------------------------------------------------
# update_stock_batch: el carrito
# -------------------------------------------------------------------------
async def test_descuenta_la_cantidad_vendida_de_cada_articulo(sesion, repo):
    articulo = construir_articulo(cantidad=50)
    repo["find_by_codigo"].return_value = articulo

    resultado = await ArticuloService.update_stock_batch(
        sesion, [ArticuloUpdate(codigo="8470001234567", cantidad_vendida=3)]
    )

    assert articulo.cantidad == 47
    assert resultado == [articulo]


async def test_un_articulo_inexistente_corta_el_lote_entero(sesion, repo):
    """Y ANTES del commit, que es lo importante: el bucle lanza, el commit
    nunca se ejecuta y SQLAlchemy manda ROLLBACK al cerrar la sesion. Si el
    commit estuviera dentro del bucle, media venta quedaria aplicada."""
    repo["find_by_codigo"].side_effect = [construir_articulo(cantidad=50), None]

    with pytest.raises(ResourceNotFoundException):
        await ArticuloService.update_stock_batch(
            sesion,
            [
                ArticuloUpdate(codigo="8470001234567", cantidad_vendida=1),
                ArticuloUpdate(codigo="NOEXISTE", cantidad_vendida=1),
            ],
        )

    sesion.commit.assert_not_awaited()


async def test_el_stock_insuficiente_es_una_excepcion_distinta(sesion, repo):
    """En el Java los dos motivos iban en el mismo RuntimeException con el
    mensaje "Artículo no encontrado o cantidad insuficiente", y los dos
    acababan en 500. Separarlos es lo que permite el 404 y el 409."""
    repo["find_by_codigo"].return_value = construir_articulo(cantidad=2)

    with pytest.raises(InsufficientStockException) as fallo:
        await ArticuloService.update_stock_batch(
            sesion, [ArticuloUpdate(codigo="8470001234567", cantidad_vendida=5)]
        )

    # El mensaje dice los dos numeros: es lo que el vendedor necesita leer.
    assert "quedan 2" in str(fallo.value)
    assert "se piden 5" in str(fallo.value)
    sesion.commit.assert_not_awaited()


async def test_vender_exactamente_todas_las_unidades_esta_permitido(sesion, repo):
    """El limite exacto. La condicion es "<", no "<=": con 2 unidades se
    pueden vender 2 y el stock queda a 0."""
    articulo = construir_articulo(cantidad=2)
    repo["find_by_codigo"].return_value = articulo

    await ArticuloService.update_stock_batch(
        sesion, [ArticuloUpdate(codigo="8470001234567", cantidad_vendida=2)]
    )

    assert articulo.cantidad == 0


async def test_un_lote_vacio_no_falla_y_no_devuelve_nada(sesion, repo):
    # El controlador convierte esta lista vacia en el 404 "No se actualizaron
    # artículos". El service no opina: no es un error suyo.
    resultado = await ArticuloService.update_stock_batch(sesion, [])

    assert resultado == []
    repo["find_by_codigo"].assert_not_awaited()


async def test_el_commit_se_hace_una_sola_vez_para_todo_el_lote(sesion, repo):
    repo["find_by_codigo"].return_value = construir_articulo(cantidad=50)

    await ArticuloService.update_stock_batch(
        sesion,
        [
            ArticuloUpdate(codigo="A", cantidad_vendida=1),
            ArticuloUpdate(codigo="B", cantidad_vendida=1),
            ArticuloUpdate(codigo="C", cantidad_vendida=1),
        ],
    )

    assert sesion.commit.await_count == 1


# -------------------------------------------------------------------------
# _generar_codigo_unico
# -------------------------------------------------------------------------
async def test_el_codigo_generado_tiene_13_digitos(sesion, repo):
    repo["codigo_en_uso"].return_value = False

    codigo = await ArticuloService._generar_codigo_unico(sesion)

    assert len(codigo) == 13
    assert codigo.isdigit()


async def test_si_el_codigo_ya_existe_genera_otro(sesion, repo):
    """El bucle while True. Se simula que los dos primeros sorteos chocan: si
    el bucle no reintentara, el INSERT moriria con el error de clave unica.
    Es un test que por HTTP no se puede escribir."""
    repo["codigo_en_uso"].side_effect = [
        True,    # el primer sorteo ya existe
        True,    # el segundo tambien
        False,   # el tercero esta libre
    ]

    codigo = await ArticuloService._generar_codigo_unico(sesion)

    assert len(codigo) == 13
    assert repo["codigo_en_uso"].await_count == 3


async def test_el_generador_no_usa_find_by_codigo(sesion, repo):
    """El que vigila el bug de unicidad del borrado logico. find_by_codigo
    filtra enabled=True y daria por libre el codigo de un retirado, que la
    UNIQUE KEY sigue contando. Si alguien vuelve a cambiar el generador a
    find_by_codigo, el test de arriba seguiria en verde (solo mira
    codigo_en_uso); este no."""
    repo["codigo_en_uso"].return_value = False

    await ArticuloService._generar_codigo_unico(sesion)

    repo["find_by_codigo"].assert_not_awaited()


async def test_insertar_pone_el_codigo_generado_y_no_el_del_cliente(sesion, repo):
    repo["codigo_en_uso"].return_value = False
    dto = ArticuloCreate(nombre="Nolotil", categoria="Analgésico", precio=5.0, cantidad=10)

    nuevo = await ArticuloService.insertar_articulo(sesion, dto)

    assert len(nuevo.codigo) == 13
    assert nuevo.nombre == "Nolotil"
    repo["save"].assert_awaited_once()
    sesion.commit.assert_awaited_once()


# -------------------------------------------------------------------------
# update_item y link_aemps
# -------------------------------------------------------------------------
async def test_update_item_solo_toca_cantidad_y_precio(sesion, repo):
    """Reutiliza el mismo DTO que updateStock, pero lee otros campos. El
    nombre y la categoria NO se tocan aunque vengan en el JSON: en el Java
    tampoco."""
    articulo = construir_articulo(nombre="Ibuprofeno 600mg", cantidad=50, precio=12.95)
    repo["find_by_codigo"].return_value = articulo

    await ArticuloService.update_item(
        sesion,
        ArticuloUpdate(codigo="8470001234567", cantidad=99, precio=1.0, nombre="OTRO NOMBRE"),
    )

    assert articulo.cantidad == 99
    assert articulo.precio == 1.0
    assert articulo.nombre == "Ibuprofeno 600mg"


async def test_link_aemps_sobre_un_articulo_que_no_existe(sesion, repo):
    repo["find_by_id"].return_value = None

    with pytest.raises(ResourceNotFoundException):
        await ArticuloService.link_aemps(sesion, 999, "67031", "Kern")

    sesion.commit.assert_not_awaited()


async def test_borrar_un_articulo_que_no_existe_no_hace_commit(sesion, repo):
    """None cubre dos casos: no existe, o ya estaba retirado (find_by_id
    filtra enabled). Los dos son 404 y ninguno toca la base."""
    repo["find_by_id"].return_value = None

    with pytest.raises(ResourceNotFoundException):
        await ArticuloService.delete_articulo_by_id(sesion, 999)

    sesion.commit.assert_not_awaited()


async def test_borrar_un_articulo_lo_retira_y_no_lo_borra(sesion, repo):
    """Borrado logico: el MISMO objeto que devuelve find_by_id pasa a
    enabled=False y se hace commit. No hay session.delete: si lo hubiera, en
    MySQL se llevaria sus ventas por la cascada."""
    articulo = construir_articulo(id=7, enabled=True)
    repo["find_by_id"].return_value = articulo

    await ArticuloService.delete_articulo_by_id(sesion, 7)

    assert articulo.enabled is False
    sesion.commit.assert_awaited_once()
    sesion.delete.assert_not_called()
