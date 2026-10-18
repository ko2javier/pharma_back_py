# tests/integration/test_articulo_cascada_mysql.py
#
# Segundo test del nivel 3, y el punto 1 de "lo que falta" de ESTRUCTURA
# §9 ter. Nacio el 2026-10-17 fijando la cascada que se comprobo a mano en
# SQL en septiembre (information_schema de Aiven):
#
#     ventas.codigo -> articulos.codigo    ON DELETE CASCADE
#     (tests/schema.sql:78, constraint fk_articulos_ventas)
#
# REESCRITO el 2026-10-18, con el borrado logico. La FK sigue en el esquema
# -- un DELETE fisico seguiria llevandose todas las ventas del articulo --,
# pero DELETE /articulos/{id} ya no manda ningun DELETE: pone enabled=False.
# Lo que estos tests fijan ahora es lo contrario de lo que fijaban ayer: el
# historial SOBREVIVE.
#
# Por que siguen en el nivel 3 y no en los 195: que la venta sobreviva solo
# lo puede decir una base con la FK de verdad. Con la sesion falsa de
# tests/conftest.py no hay FK que dispare, y con un create_all() tampoco
# (los modelos no la declaran): el test pasaria en verde tanto con el
# borrado logico como con el fisico. Es el razonamiento de ESTRUCTURA §9 ter
# "Por que un schema.sql y no create_all".
from datetime import date, time

import pytest
from sqlalchemy import func, select

from app.models.articulo_model import Articulos
from app.models.user_model import Users
from app.repositories.articulo_repository import ArticuloRepository
from app.services.articulo_service import ArticuloService
from app.models.venta_cancelada_model import CancellationStatus, VentaCancelada
from app.models.venta_model import Ventas

# Dos articulos distintos. El segundo es el CONTROL: retirar uno no puede
# afectar al otro.
CODIGO_BORRADO = "8470001111111"
CODIGO_INTACTO = "8470002222222"


async def _preparar(sesion) -> dict[str, int]:
    """Deja en MySQL el escenario completo y devuelve los id que hacen falta.

    Lo que queda escrito:
      * un usuario (fk_usuario_ventas obliga a que exista)
      * articulo A, con DOS ventas
      * articulo B, con UNA venta
      * una fila en ventas_canceladas, que no cuelga de ningun articulo

    El commit() del final no es decorativo: MySQL va en REPEATABLE READ, y
    si la sesion del test se quedara dentro de una transaccion abierta,
    seguiria viendo la foto de ANTES de la peticion -- y el test
    afirmaria que el articulo sigue activo. Con el commit, la primera
    lectura de despues abre transaccion nueva y ve lo que hay de verdad.
    """
    sesion.add(Users(username="tester", password="x", enabled=True, permiso="ADMIN"))

    articulo_a = Articulos(nombre="Ibuprofeno 600mg", categoria="Antiinflamatorio",
                           precio=12.95, cantidad=50, codigo=CODIGO_BORRADO)
    articulo_b = Articulos(nombre="Paracetamol 1g", categoria="Analgesico",
                           precio=4.50, cantidad=80, codigo=CODIGO_INTACTO)
    sesion.add_all([articulo_a, articulo_b])
    await sesion.flush()

    # OJO: el atributo del modelo es 'username' pero la columna se llama
    # 'id_username' (app/models/venta_model.py:21). Aqui va el del modelo.
    sesion.add_all([
        Ventas(fecha=date(2026, 10, 17), hora=time(10, 0), username="tester",
               dnicliente="11111111A", nameproducto="Ibuprofeno 600mg",
               cantidad=1, importe=12.95, codigo=CODIGO_BORRADO),
        Ventas(fecha=date(2026, 10, 17), hora=time(11, 0), username="tester",
               dnicliente="22222222B", nameproducto="Ibuprofeno 600mg",
               cantidad=2, importe=25.90, codigo=CODIGO_BORRADO),
        Ventas(fecha=date(2026, 10, 17), hora=time(12, 0), username="tester",
               dnicliente="33333333C", nameproducto="Paracetamol 1g",
               cantidad=1, importe=4.50, codigo=CODIGO_INTACTO),
    ])

    # ventas_canceladas no tiene ni FK ni columna 'codigo'
    # (tests/schema.sql:82-91): es una tabla de auditoria suelta. Ni con el
    # DELETE fisico la tocaba la cascada.
    sesion.add(VentaCancelada(nombre_producto="Ibuprofeno 600mg", cantidad=3,
                              importe=38.85, responsable="admin",
                              status=CancellationStatus.CANCELLED))
    await sesion.commit()
    return {"a": articulo_a.id, "b": articulo_b.id}


async def _contar(sesion, modelo) -> int:
    return (await sesion.execute(select(func.count()).select_from(modelo))).scalar_one()


async def _codigos_de_ventas(sesion) -> list[str]:
    return list((await sesion.execute(select(Ventas.codigo).order_by(Ventas.id))).scalars())


async def _enabled_de(sesion, articulo_id: int) -> bool:
    """Lee la columna, no el objeto: el de la sesion del test es la foto de
    _preparar, y la peticion modifico OTRA sesion."""
    return (await sesion.execute(
        select(Articulos.enabled).where(Articulos.id == articulo_id)
    )).scalar_one()


# -------------------------------------------------------------------------
# Retirar un articulo: desaparece, pero su fila y sus ventas se quedan
# -------------------------------------------------------------------------
async def test_retirar_articulo_conserva_sus_ventas(client, autenticar, sesion):
    ids = await _preparar(sesion)
    autenticar()

    r = await client.delete(f"/articulos/{ids['a']}")

    assert r.status_code == 204
    assert r.content == b""  # 204 sin cuerpo, como ResponseEntity.noContent()

    # Ayer, con el DELETE fisico, aqui quedaban 1 venta y 1 articulo.
    assert await _contar(sesion, Ventas) == 3
    assert await _codigos_de_ventas(sesion) == [CODIGO_BORRADO, CODIGO_BORRADO, CODIGO_INTACTO]
    assert await _contar(sesion, Articulos) == 2
    assert await _enabled_de(sesion, ids["a"]) is False
    assert await _enabled_de(sesion, ids["b"]) is True


async def test_retirar_articulo_no_toca_ventas_canceladas(client, autenticar, sesion):
    """Las cancelaciones guardan el nombre del producto como texto suelto,
    sin FK. Retirar un producto del catalogo no puede borrar el rastro de sus
    cancelaciones -- ni ahora ni con el DELETE fisico de antes."""
    ids = await _preparar(sesion)
    autenticar()

    r = await client.delete(f"/articulos/{ids['a']}")

    assert r.status_code == 204
    assert await _contar(sesion, VentaCancelada) == 1
    cancelacion = (await sesion.execute(select(VentaCancelada))).scalar_one()
    assert cancelacion.nombre_producto == "Ibuprofeno 600mg"


async def test_el_retirado_desaparece_de_all(client, autenticar, sesion):
    """La decision del 2026-10-18: todos los GET devuelven solo los activos.
    Es lo que hace que desaparezca del almacen del Angular, que solo lee
    /All."""
    ids = await _preparar(sesion)
    autenticar()

    await client.delete(f"/articulos/{ids['a']}")
    r = await client.get("/articulos/All")

    assert r.status_code == 200
    assert [a["codigo"] for a in r.json()] == [CODIGO_INTACTO]


async def test_retirar_dos_veces_da_404_y_no_duplica_el_log(client, autenticar, sesion, log):
    """'log' es el espia de tests/conftest.py:110, autouse tambien aqui: en
    los tests ActivityLogService.log nunca escribe en activity_log. Por eso se
    le pregunta al espia y no a la tabla, que siempre esta vacia."""
    ids = await _preparar(sesion)
    autenticar()

    primera = await client.delete(f"/articulos/{ids['a']}")
    segunda = await client.delete(f"/articulos/{ids['a']}")

    assert primera.status_code == 204
    assert segunda.status_code == 404
    # Una sola llamada: la segunda peticion corta en el 404 antes del log.
    log.assert_awaited_once()
    assert log.await_args.args[2] == "DELETE_PRODUCT"


# -------------------------------------------------------------------------
# Lo que solo se ve con la UNIQUE KEY de verdad
# -------------------------------------------------------------------------
async def test_el_codigo_de_un_retirado_sigue_ocupado(client, autenticar, sesion):
    """El bug de unicidad. find_by_codigo ya no ve el retirado, pero la UNIQUE
    KEY codigo_unico si: si el generador se fiara de find_by_codigo, el
    INSERT moriria con IntegrityError. codigo_en_uso tiene que decir True."""
    ids = await _preparar(sesion)
    autenticar()
    await client.delete(f"/articulos/{ids['a']}")

    assert await ArticuloRepository.find_by_codigo(sesion, CODIGO_BORRADO) is None
    assert await ArticuloRepository.codigo_en_uso(sesion, CODIGO_BORRADO) is True


async def test_un_nombre_retirado_se_puede_volver_a_dar_de_alta(client, autenticar, sesion):
    """search_by_keyword es lo que usa el 409 "El producto ya existe en el
    inventario" de /cima/validar (cima_controller.py:84). Si viera al
    retirado, el producto no se podria volver a dar de alta nunca. No se
    prueba por HTTP porque /cima/validar llama a AEMPS y a la IA."""
    ids = await _preparar(sesion)
    autenticar()
    await client.delete(f"/articulos/{ids['a']}")

    assert await ArticuloService.search_by_keyword(sesion, "Ibuprofeno") == []


# -------------------------------------------------------------------------
# El contrato del Python (404), que NO es el del Java (500)
# -------------------------------------------------------------------------
async def test_borrar_articulo_inexistente_da_404_y_no_toca_nada(client, autenticar, sesion):
    """Divergencia deliberada del paso 8, no un descuido.

    El Java lanza un RuntimeException pelado (ArticuloService.java:96) que
    acaba en el @ExceptionHandler(Exception.class) generico de
    GlobalExceptionHandler.java:38 -> 500 con {"error": "Error interno del
    servidor"}. El Python lanza ResourceNotFoundException
    (app/services/articulo_service.py, delete_articulo_by_id) y
    app/exceptions/handlers.py:31 la traduce a 404. Se fija el 404:
    replicar el 500 seria reintroducir el fallo a proposito."""
    await _preparar(sesion)
    autenticar()

    r = await client.delete("/articulos/999999")

    assert r.status_code == 404
    assert r.json() == {"error": "Artículo no encontrado con id: 999999"}
    assert await _contar(sesion, Articulos) == 2
    assert await _contar(sesion, Ventas) == 3
    assert await _contar(sesion, VentaCancelada) == 1
