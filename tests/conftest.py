# tests/conftest.py
#
# El equivalente de la clase base de tests de Spring: lo que alli eran
# @SpringBootTest + @MockBean + @BeforeEach, aqui son fixtures que pytest
# inyecta por NOMBRE en cada test que las pida como parametro. No hay que
# importarlas: pytest descubre este fichero solo.
#
# NINGUN test de esta bateria toca Aiven. Son los niveles 1 y 2 de ESTRUCTURA
# §9: unitario con mocks y contrato HTTP. Medido tras importar la app,
# engine.pool.checkedout() == 0 — el engine se construye al importar, pero
# SQLAlchemy es perezoso y no abre nada hasta la primera consulta, y aqui la
# sesion va siempre sustituida.
from datetime import date, datetime, time
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_http_client
from app.core.database import get_db
from app.main import app
from app.models.activity_log_model import ActivityLog
from app.models.articulo_model import Articulos
from app.models.user_model import Users
from app.models.venta_cancelada_model import CancellationStatus, VentaCancelada
from app.models.venta_model import Ventas
from app.services.activity_log_service import ActivityLogService


# -------------------------------------------------------------------------
# 1. El MockMvc
# -------------------------------------------------------------------------
@pytest.fixture
async def client():
    """Cliente httpx contra la app en memoria. Es el MockMvc de Spring.

    No hay red ni servidor: ASGITransport llama a la aplicacion como si fuera
    una funcion. Tres decisiones, las tres medidas:

      * raise_app_exceptions=False — es el raise_server_exceptions=False del
        TestClient. Starlette, DESPUES de pasar la excepcion por el handler
        generico, siempre la vuelve a lanzar para que el servidor pueda
        registrarla. Medido sobre una ruta que hace raise RuntimeError:
            True (por defecto) -> el test recibe el RuntimeError, sin respuesta
            False              -> 500 {"error":"Error interno del servidor"}
        Sin esto no se puede probar el 500 de la IA (test_cima_controller).
      * base_url — ASGITransport no habla por red, pero httpx exige una URL
        absoluta: sin esto, client.get("/") es un error de httpx, no un 404.
      * ambito de funcion — un cliente por test, para no depender de en que
        bucle de eventos se creo. No cuesta nada: no hay sockets que abrir.

    OJO: ASGITransport NO ejecuta el lifespan de main.py. Medido:
    hasattr(app.state, "http_client") es False dentro de los tests, asi que
    las pruebas de /api/cima tienen que sustituir get_http_client (fixture
    cliente_http, mas abajo).
    """
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# -------------------------------------------------------------------------
# 2. Limpiar los @MockBean entre tests
# -------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def limpiar_overrides():
    """Vacia app.dependency_overrides DESPUES de cada test.

    'app' es un singleton de modulo: se importa una vez y lo comparten todos
    los tests de la carpeta. Un override que se quede puesto autentica al test
    siguiente sin que nadie lo haya pedido, y ese test pasa en verde probando
    otra cosa. En Spring de esto se encargaba el framework rehaciendo el
    contexto; aqui no hay nadie que lo haga.

    autouse=True: se aplica a todos los tests sin declararla.
    """
    yield
    app.dependency_overrides.clear()


# -------------------------------------------------------------------------
# 3. La sesion de base de datos falsa
# -------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def sesion() -> AsyncMock:
    """AsyncMock en lugar de la AsyncSession, y sustituye get_db en TODA la app.

    autouse=True a proposito: asi ninguna ruta puede abrir una conexion a
    Aiven por descuido, ni siquiera un test que se olvide de pedir la fixture.

    spec=AsyncSession no es decorativo: con el, sesion.commti() es un
    AttributeError en el test; sin el es un mock nuevo que devuelve otro mock y
    el test pasa en verde. Es la red contra el bug que mas veces ha aparecido
    en este proyecto: el nombre plausible que no existe.

    El override es una lambda y no un generador async: dependency_overrides
    acepta cualquier callable, no exige respetar la forma de la dependencia
    original (get_db si es un generador async).
    """
    falsa = AsyncMock(spec=AsyncSession)
    app.dependency_overrides[get_db] = lambda: falsa
    return falsa


# -------------------------------------------------------------------------
# 4. El activity_log, siempre mockeado
# -------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def log(monkeypatch) -> AsyncMock:
    """Sustituye ActivityLogService.log en todos los tests.

    autouse porque es una ESCRITURA: nueve endpoints la llaman, y sin esto un
    test tocaria la tabla activity_log de verdad. Los tests que quieran
    comprobar QUE se registro piden la fixture por nombre y miran
    log.await_args.

    monkeypatch deshace el parche al terminar cada test, sin tener que
    acordarse (es el @AfterEach gratis).
    """
    espia = AsyncMock(return_value=None)
    monkeypatch.setattr(ActivityLogService, "log", espia)
    return espia


# -------------------------------------------------------------------------
# 5. Autenticacion: el @MockBean de la seguridad
# -------------------------------------------------------------------------
def construir_usuario(
    username: str = "tester",
    permiso: str = "ADMIN",
    enabled: bool = True,
    id: int = 1,
) -> Users:
    """Una entidad Users en memoria: ni sesion, ni INSERT, ni Aiven.

    SQLAlchemy no obliga a pasar por la base de datos — un objeto 'transient'
    es un POJO normal, como un new Users() en Java antes de persistirlo.
    """
    user = Users()
    user.id = id
    user.username = username
    user.password = "$2a$10$hash.que.nadie.verifica"
    user.permiso = permiso
    user.enabled = enabled
    return user


@pytest.fixture
def autenticar():
    """Devuelve una funcion que "pone el token": el @MockBean de la seguridad.

        async def test_algo(client, autenticar):
            autenticar(permiso="SUPERADMIN")
            r = await client.get("/activity-log/all")

    Sustituye get_current_user, asi que desde esa linea toda la app cree que
    llama ese usuario — incluido require_role("SUPERADMIN"), que depende de
    get_current_user por dentro y queda cubierto con el mismo override.

    Es una fabrica (una fixture que devuelve una funcion) y no una fixture a
    secas porque cada test necesita un ROL distinto, y una fixture no recibe
    parametros del test que la pide.
    """

    def _autenticar(
        permiso: str = "ADMIN",
        username: str = "tester",
        enabled: bool = True,
        id: int = 1,
    ) -> Users:
        user = construir_usuario(username=username, permiso=permiso, enabled=enabled, id=id)
        app.dependency_overrides[get_current_user] = lambda: user
        return user

    return _autenticar


# -------------------------------------------------------------------------
# 6. El cliente HTTP externo (AEMPS / IA), falso
# -------------------------------------------------------------------------
@pytest.fixture
def cliente_http():
    """Devuelve una funcion que monta un httpx.AsyncClient de mentira.

        async def test_x(client, cliente_http):
            def responder(peticion: httpx.Request) -> httpx.Response:
                return httpx.Response(200, text='{"ok":1}')
            peticiones = cliente_http(responder)

    httpx.MockTransport intercepta la peticion ANTES de salir a la red y
    ejecuta esa funcion. Se eligio asi en vez de mockear CimaService entero
    porque de este modo el test recorre el service de verdad (el
    raise_for_status, el response.text crudo, los params) y solo finge AEMPS.

    Devuelve la lista donde se van guardando las peticiones salientes, para
    poder comprobar que el nombre viajo en params= y no concatenado.
    """
    peticiones: list[httpx.Request] = []

    def _montar(responder):
        def envoltorio(peticion: httpx.Request) -> httpx.Response:
            peticiones.append(peticion)
            return responder(peticion)

        falso = httpx.AsyncClient(transport=httpx.MockTransport(envoltorio))
        app.dependency_overrides[get_http_client] = lambda: falso
        return peticiones

    return _montar


# -------------------------------------------------------------------------
# 7. Fabricas de entidades (los "object mother" de los tests)
# -------------------------------------------------------------------------
def construir_articulo(
    id: int = 1,
    nombre: str = "Ibuprofeno 600mg",
    categoria: str = "Antiinflamatorio",
    precio: float = 12.95,
    cantidad: int = 50,
    codigo: str = "8470001234567",
    version: int = 0,
    aemps_code: str | None = "67031",
    laboratorio: str | None = "Kern Pharma",
    enabled: bool = True,
) -> Articulos:
    a = Articulos()
    a.id = id
    a.nombre = nombre
    a.categoria = categoria
    a.precio = precio
    a.cantidad = cantidad
    a.codigo = codigo
    a.version = version
    a.aemps_code = aemps_code
    a.laboratorio = laboratorio
    a.enabled = enabled
    return a


def construir_venta(
    id: int = 1,
    username: str = "tester",
    dnicliente: str = "12345678A",
    nameproducto: str = "Ibuprofeno 600mg",
    cantidad: int = 2,
    importe: float = 25.90,
    codigo: str = "8470001234567",
) -> Ventas:
    v = Ventas()
    v.id = id
    v.fecha = date(2026, 10, 11)
    v.hora = time(13, 45, 0)
    v.username = username
    v.dnicliente = dnicliente
    v.nameproducto = nameproducto
    v.cantidad = cantidad
    v.importe = importe
    v.codigo = codigo
    return v


def construir_cancelacion(
    id: int = 1,
    nombre_producto: str | None = "Ibuprofeno 600mg",
    cantidad: int = 2,
    importe: float | None = 25.90,
    responsable: str | None = "admin",
    status: CancellationStatus | None = CancellationStatus.CANCELLED,
) -> VentaCancelada:
    c = VentaCancelada()
    c.id = id
    c.nombre_producto = nombre_producto
    c.cantidad = cantidad
    c.importe = importe
    c.responsable = responsable
    c.fecha = datetime(2026, 10, 11, 13, 45, 0)
    c.status = status
    return c


def construir_log(
    id: int = 1,
    username: str = "tester",
    action: str = "LOGIN_SUCCESS",
    detail: str | None = "tester",
    ip_address: str | None = "127.0.0.1",
) -> ActivityLog:
    registro = ActivityLog()
    registro.id = id
    registro.username = username
    registro.action = action
    registro.detail = detail
    registro.ip_address = ip_address
    registro.fecha = date(2026, 10, 11)
    registro.hora = time(13, 45, 0)
    return registro
