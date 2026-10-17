# tests/integration/test_articulo_cascada_mysql.py
#
# Segundo test del nivel 3, y el punto 1 de "lo que falta" de ESTRUCTURA
# §9 ter. Fija la cascada que se comprobo a mano en SQL en septiembre
# (information_schema de Aiven, citado en articulo_controller.py:132-142):
#
#     ventas.codigo -> articulos.codigo    ON DELETE CASCADE
#     (tests/schema.sql:77, constraint fk_articulos_ventas)
#
# Borrar un articulo se lleva por delante TODAS sus ventas. Es borrado
# fisico y lo hace MySQL, no el codigo:
#
#   * Articulos (app/models/articulo_model.py) no declara ningun
#     ForeignKey ni relationship().
#   * Articulos.java tampoco tiene @OneToMany ni cascade=.
#
# O sea que ni SQLAlchemy ni Hibernate saben que esto pasa. El DELETE que
# sale de ArticuloRepository.delete_by_id (app/repositories/
# articulo_repository.py:69-73) es un DELETE de UNA fila de articulos; las
# ventas desaparecen en el servidor, sin que el ORM se entere.
#
# POR ESO ESTE TEST SOLO PUEDE VIVIR AQUI. Con la sesion falsa de
# tests/conftest.py no hay base de datos que aplique la FK, y con un
# Base.metadata.create_all() el esquema no tendria la constraint (los
# modelos no la declaran): en los dos casos el test pasaria en verde
# habiendo probado NADA. Necesita el schema.sql real. Es el mismo
# razonamiento de ESTRUCTURA §9 ter "Por que un schema.sql y no create_all".
from datetime import date, time

import pytest
from sqlalchemy import func, select

from app.models.articulo_model import Articulos
from app.models.user_model import Users
from app.models.venta_cancelada_model import CancellationStatus, VentaCancelada
from app.models.venta_model import Ventas

# Dos articulos distintos. El segundo es el CONTROL: si la cascada se
# llevara tambien sus ventas, no seria una cascada, seria un TRUNCATE.
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
    seguiria viendo la foto de ANTES del DELETE que hace la peticion -- y
    el test afirmaria que la cascada no ocurrio. Con el commit, la primera
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
    # (tests/schema.sql:81-90): es una tabla de auditoria suelta. Si la
    # cascada la tocara, se estaria borrando el historial de cancelaciones
    # al retirar un producto del catalogo.
    sesion.add(VentaCancelada(nombre_producto="Ibuprofeno 600mg", cantidad=3,
                              importe=38.85, responsable="admin",
                              status=CancellationStatus.CANCELLED))
    await sesion.commit()
    return {"a": articulo_a.id, "b": articulo_b.id}


async def _contar(sesion, modelo) -> int:
    return (await sesion.execute(select(func.count()).select_from(modelo))).scalar_one()


async def _codigos_de_ventas(sesion) -> list[str]:
    return list((await sesion.execute(select(Ventas.codigo).order_by(Ventas.id))).scalars())


# -------------------------------------------------------------------------
# La cascada: borrar el articulo se lleva SUS ventas, y solo las suyas
# -------------------------------------------------------------------------
async def test_borrar_articulo_arrastra_sus_ventas(client, autenticar, sesion):
    ids = await _preparar(sesion)
    autenticar()

    r = await client.delete(f"/articulos/{ids['a']}")

    assert r.status_code == 204
    assert r.content == b""  # 204 sin cuerpo, como ResponseEntity.noContent()

    # Antes habia 3 ventas; quedan las del articulo que NO se borro.
    # Esto es lo que ningun mock puede decir: el DELETE que mando
    # SQLAlchemy afectaba a una fila de 'articulos'.
    assert await _contar(sesion, Ventas) == 1
    assert await _codigos_de_ventas(sesion) == [CODIGO_INTACTO]
    assert await _contar(sesion, Articulos) == 1


# -------------------------------------------------------------------------
# El limite de la cascada: ventas_canceladas no se entera
# -------------------------------------------------------------------------
async def test_borrar_articulo_no_toca_ventas_canceladas(client, autenticar, sesion):
    """Las dos tablas se llaman casi igual y hacen lo contrario ante el
    mismo DELETE. 'ventas' cuelga de articulos.codigo y cae; 'ventas_
    canceladas' guarda el nombre del producto como texto suelto y sobrevive.
    Es justo lo que se quiere de un registro de auditoria: retirar un
    producto del catalogo no puede borrar el rastro de sus cancelaciones."""
    ids = await _preparar(sesion)
    autenticar()

    r = await client.delete(f"/articulos/{ids['a']}")

    assert r.status_code == 204
    assert await _contar(sesion, VentaCancelada) == 1
    cancelacion = (await sesion.execute(select(VentaCancelada))).scalar_one()
    assert cancelacion.nombre_producto == "Ibuprofeno 600mg"


# -------------------------------------------------------------------------
# El contrato del Python (404), que NO es el del Java (500)
# -------------------------------------------------------------------------
async def test_borrar_articulo_inexistente_da_404_y_no_borra_nada(client, autenticar, sesion):
    """Divergencia deliberada del paso 8, no un descuido.

    El Java lanza un RuntimeException pelado (ArticuloService.java:96) que
    acaba en el @ExceptionHandler(Exception.class) generico de
    GlobalExceptionHandler.java:38 -> 500 con {"error": "Error interno del
    servidor"}. El Python lanza ResourceNotFoundException
    (app/services/articulo_service.py:119) y app/exceptions/handlers.py:31
    la traduce a 404. Se fija el 404: replicar el 500 seria reintroducir el
    fallo a proposito.

    El 'no borra nada' es lo que justifica que este test este en el nivel 3
    y no entre los 195: comprueba que el exists_by_id del service corta
    ANTES de mandar ningun DELETE a MySQL."""
    await _preparar(sesion)
    autenticar()

    r = await client.delete("/articulos/999999")

    assert r.status_code == 404
    assert r.json() == {"error": "Artículo no encontrado con id: 999999"}
    assert await _contar(sesion, Articulos) == 2
    assert await _contar(sesion, Ventas) == 3
    assert await _contar(sesion, VentaCancelada) == 1
