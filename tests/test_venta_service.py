# tests/test_venta_service.py
#
# NIVEL 1: el service de ventas con los repositorios sustituidos.
#
# Lo que importa aqui es cancelar_venta, que es la UNICA transaccion de
# varias escrituras del proyecto: devuelve al stock lo vendido (desde el
# 2026-10-18), copia la venta al historial de cancelaciones y borra la
# original. Si se partiera en varios commits, un fallo intermedio dejaria la
# venta duplicada (en ventas y en canceladas), desaparecida de las dos, o el
# stock repuesto sin cancelacion. Por HTTP esto no se ve: el codigo seria 200
# igual.
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.exceptions.custom import ResourceNotFoundException
from app.models.venta_cancelada_model import CancellationStatus
from app.repositories.articulo_repository import ArticuloRepository
from app.repositories.venta_cancelada_repository import VentaCanceladaRepository
from app.repositories.venta_repository import VentaRepository
from app.schemas.venta_schema import VentaCreate
from app.services.venta_service import VentaService
from tests.conftest import construir_articulo, construir_venta


@pytest.fixture
def repo(monkeypatch):
    espias = {}
    for nombre in ("find_all", "find_by_username", "find_by_id", "save", "delete"):
        espia = AsyncMock()
        monkeypatch.setattr(VentaRepository, nombre, espia)
        espias[nombre] = espia
    espia_cancelada = AsyncMock()
    monkeypatch.setattr(VentaCanceladaRepository, "save", espia_cancelada)
    espias["save_cancelada"] = espia_cancelada
    # El articulo al que cancelar_venta devuelve el stock. Por defecto uno
    # activo con 50 unidades; sin este espia, el repositorio de verdad correria
    # contra la sesion falsa y devolveria un mock en vez de un articulo.
    espia_articulo = AsyncMock(return_value=construir_articulo(cantidad=50))
    monkeypatch.setattr(ArticuloRepository, "find_by_codigo_incluso_retirados", espia_articulo)
    espias["articulo"] = espia_articulo
    return espias


VENTA_DTO = VentaCreate(
    dnicliente="12345678A",
    nameproducto="Ibuprofeno 600mg",
    cantidad=2,
    importe=25.90,
    codigo="8470001234567",
)


# -------------------------------------------------------------------------
# registrar
# -------------------------------------------------------------------------
async def test_la_fecha_y_la_hora_las_pone_el_servidor(sesion, repo):
    """VentaCreate no las declara. Si viniesen del cliente, se podrian
    registrar ventas con fecha de ayer para cuadrar una caja."""
    venta = await VentaService.registrar_venta(sesion, "vendedor7", VENTA_DTO)

    assert venta.fecha == date.today()
    assert venta.hora is not None
    assert venta.username == "vendedor7"


async def test_registrar_una_lista_hace_un_solo_commit(sesion, repo):
    """Las tres ventas del carrito entran o no entra ninguna. Con un commit
    por iteracion, un fallo en la tercera dejaria las dos primeras cobradas."""
    await VentaService.registrar_ventas(sesion, "vendedor7", [VENTA_DTO, VENTA_DTO, VENTA_DTO])

    assert repo["save"].await_count == 3
    assert sesion.commit.await_count == 1


async def test_registrar_no_toca_el_stock(sesion, repo):
    """Deja constancia de la deuda heredada del Java: VentaService inyecta el
    repositorio de articulos y no lo usa. El descuento lo hace el frontend en
    una segunda peticion a /articulos/updateStock, sin transaccion comun — si
    esa segunda falla, la venta queda registrada y el stock sin tocar."""
    venta = await VentaService.registrar_venta(sesion, "vendedor7", VENTA_DTO)

    # El objeto creado no tiene ni rastro del articulo: solo copia el codigo.
    assert venta.codigo == "8470001234567"
    assert repo["save"].await_count == 1


# -------------------------------------------------------------------------
# cancelar_venta: la transaccion de varias escrituras
# -------------------------------------------------------------------------
async def test_cancelar_copia_la_venta_al_historial_y_borra_la_original(sesion, repo):
    original = construir_venta(id=42, nameproducto="Nolotil", cantidad=3, importe=15.0)
    repo["find_by_id"].return_value = original

    await VentaService.cancelar_venta(sesion, 42, "el_jefe")

    # 1. Se guardo la cancelacion con los datos copiados de la venta.
    copia = repo["save_cancelada"].await_args.args[1]
    assert copia.nombre_producto == "Nolotil"
    assert copia.cantidad == 3
    assert copia.importe == 15.0
    assert copia.status == CancellationStatus.CANCELLED
    # 2. Y se borro la original.
    repo["delete"].assert_awaited_once()
    assert repo["delete"].await_args.args[1] is original


async def test_las_escrituras_van_en_un_solo_commit(sesion, repo):
    """Es el @Transactional. Un commit, no dos: si el DELETE fallara despues
    de un commit del INSERT, la venta estaria a la vez cancelada y viva."""
    repo["find_by_id"].return_value = construir_venta(id=42)

    await VentaService.cancelar_venta(sesion, 42, "el_jefe")

    assert sesion.commit.await_count == 1


async def test_el_responsable_que_firma_es_el_que_se_pasa_por_parametro(sesion, repo):
    """Y no el usuario autenticado: son dos cosas distintas a proposito. El
    Java tampoco lo valida — se puede firmar una cancelacion con el nombre de
    otro —, por eso el activity_log guarda ademas el username del token."""
    repo["find_by_id"].return_value = construir_venta(id=42)

    await VentaService.cancelar_venta(sesion, 42, "el_jefe")

    copia = repo["save_cancelada"].await_args.args[1]
    assert copia.responsable == "el_jefe"


async def test_cancelar_una_venta_inexistente_no_escribe_nada(sesion, repo):
    """Y lanza la excepcion del 404, no un ValueError: eso daba 500."""
    repo["find_by_id"].return_value = None

    with pytest.raises(ResourceNotFoundException):
        await VentaService.cancelar_venta(sesion, 999, "el_jefe")

    repo["save_cancelada"].assert_not_awaited()
    repo["delete"].assert_not_awaited()
    repo["articulo"].assert_not_awaited()
    sesion.commit.assert_not_awaited()


# -------------------------------------------------------------------------
# cancelar_venta: devolver al stock lo vendido (2026-10-18)
# -------------------------------------------------------------------------
async def test_cancelar_devuelve_al_stock_lo_vendido(sesion, repo):
    articulo = construir_articulo(cantidad=50, codigo="8470001234567")
    repo["articulo"].return_value = articulo
    repo["find_by_id"].return_value = construir_venta(id=42, cantidad=3, codigo="8470001234567")

    await VentaService.cancelar_venta(sesion, 42, "el_jefe")

    assert articulo.cantidad == 53
    # Se busca por el codigo de la VENTA, que es la FK, y no por el nombre.
    assert repo["articulo"].await_args.args[1] == "8470001234567"


async def test_cancelar_repone_igual_si_el_articulo_esta_retirado(sesion, repo):
    """La decision del 2026-10-18: retirado o no, se hace lo mismo. El
    retirado sigue retirado -- solo cambia su cantidad."""
    articulo = construir_articulo(cantidad=50, enabled=False)
    repo["articulo"].return_value = articulo
    repo["find_by_id"].return_value = construir_venta(id=42, cantidad=3)

    await VentaService.cancelar_venta(sesion, 42, "el_jefe")

    assert articulo.cantidad == 53
    assert articulo.enabled is False


async def test_si_el_articulo_no_existe_no_cancela_sin_reponer(sesion, repo):
    """No deberia pasar nunca: la FK lo impide. Si pasa, revienta antes de
    escribir nada, en vez de cancelar en silencio sin devolver el stock."""
    repo["articulo"].return_value = None
    repo["find_by_id"].return_value = construir_venta(id=42)

    with pytest.raises(RuntimeError):
        await VentaService.cancelar_venta(sesion, 42, "el_jefe")

    repo["save_cancelada"].assert_not_awaited()
    repo["delete"].assert_not_awaited()
    sesion.commit.assert_not_awaited()
