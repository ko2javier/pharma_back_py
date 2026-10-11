# tests/test_cima_controller.py
#
# NIVEL 2 + el service de verdad: los 3 endpoints de /api/cima.
#
# Aqui NO se mockea CimaService ni IaService. Se sustituye solo el
# httpx.AsyncClient (fixture cliente_http, con httpx.MockTransport), asi que
# el test recorre el service entero —el raise_for_status, el response.text
# crudo, los params— y solo finge la respuesta de AEMPS y la del micro de IA.
# Es lo unico que distingue un 502 de verdad de uno de mentira.
#
# LA ASIMETRIA QUE HAY QUE REPLICAR, leida en el Java antes de escribirlo:
#
#   AEMPS falla  -> 502   (CimaController tiene try/catch de RestTemplate)
#   La IA falla  -> 500   (CimaController.java:105 NO tiene try; sube al
#                          handler generico)
#
# No es un descuido del espejo: el documento del proyecto decia que
# ExternalServiceException cubria las dos y estaba equivocado. Y de ahi sale
# la otra regla: si la IA falla, el IA_MATCH no se escribe, porque en el Java
# el log va despues de la llamada y sin try.
#
# Tres trampas de pasar de RestTemplate a httpx que estos tests fijan:
#   1. httpx NO lanza excepcion con un 4xx/5xx (RestTemplate si): sin
#      raise_for_status, una pagina de error 503 se reenviaria al Angular como
#      respuesta buena.
#   2. Los parametros van en params=, nunca concatenados. El Java hace
#      "?nombre=" + nombre, asi que un & en el nombre cuela parametros.
#   3. Devolver un str desde el endpoint lo serializa OTRA VEZ como JSON: el
#      Angular recibiria un string con el JSON dentro.
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import get_settings
from app.services.articulo_service import ArticuloService
from tests.conftest import construir_articulo

settings = get_settings()

AEMPS = "cima.aemps.es"
RESPUESTA_AEMPS = '{"nregistro":"67031","nombre":"IBUPROFENO KERN PHARMA 600 MG"}'


@pytest.fixture
def inventario(monkeypatch):
    """Sustituye la busqueda en el inventario propio (la parte que toca BD).

    Por defecto devuelve [] = el producto no esta en el almacen, que es el
    camino normal de /validar.
    """
    espia = AsyncMock(return_value=[])
    monkeypatch.setattr(ArticuloService, "search_by_keyword", espia)
    return espia


def es_ia(peticion: httpx.Request) -> bool:
    return "/api/v1/ia/match" in str(peticion.url)


# -------------------------------------------------------------------------
# GET /api/cima/medicamento
# -------------------------------------------------------------------------
async def test_medicamento_devuelve_el_json_de_aemps_sin_doble_serializar(
    client, autenticar, cliente_http
):
    """El fallo que esto evita: si el endpoint devolviera el str pelado,
    FastAPI lo serializaria otra vez y el Angular recibiria la cadena
    "{\\"nregistro\\"...}" en vez de un objeto. Se comprueba con r.json(), que
    tiene que dar un dict."""
    autenticar()
    cliente_http(lambda p: httpx.Response(200, text=RESPUESTA_AEMPS))

    r = await client.get("/api/cima/medicamento?nregistro=67031")

    assert r.status_code == 200
    assert r.text == RESPUESTA_AEMPS
    assert isinstance(r.json(), dict)
    assert r.json()["nregistro"] == "67031"


async def test_el_nregistro_viaja_en_params_y_no_concatenado(client, autenticar, cliente_http):
    autenticar()
    peticiones = cliente_http(lambda p: httpx.Response(200, text="{}"))

    await client.get("/api/cima/medicamento?nregistro=67031")

    assert len(peticiones) == 1
    saliente = peticiones[0]
    assert AEMPS in saliente.url.host
    assert saliente.url.path.endswith("/medicamento")
    assert dict(saliente.url.params) == {"nregistro": "67031"}


async def test_nregistro_inexistente_devuelve_200_vacio(client, autenticar, cliente_http):
    """Medido contra AEMPS de verdad: con un nregistro que no existe responde
    204 con cuerpo vacio. Por eso el service devuelve response.text crudo y no
    response.json(): parsear "" seria un ValueError -> 502 donde el Java da
    200 vacio."""
    autenticar()
    cliente_http(lambda p: httpx.Response(204))

    r = await client.get("/api/cima/medicamento?nregistro=00000")

    assert r.status_code == 200
    assert r.text == ""


async def test_aemps_caido_da_502(client, autenticar, cliente_http):
    autenticar()
    cliente_http(lambda p: httpx.Response(503, text="<html>Service Unavailable</html>"))

    r = await client.get("/api/cima/medicamento?nregistro=67031")

    assert r.status_code == 502
    assert r.json() == {"error": "Error conectando con AEMPS"}


async def test_aemps_inalcanzable_da_502(client, autenticar, cliente_http):
    """Caso distinto del anterior: aqui no hay respuesta HTTP, falla la
    conexion (DNS, red, timeout). httpx lanza una subclase de httpx.HTTPError
    y el service la traduce igual."""
    autenticar()

    def explota(peticion):
        raise httpx.ConnectError("sin red", request=peticion)

    cliente_http(explota)

    r = await client.get("/api/cima/medicamento?nregistro=67031")

    assert r.status_code == 502


async def test_una_api_key_mala_no_llega_al_angular_como_200(client, autenticar, cliente_http):
    """httpx no lanza excepcion con un 401, al reves que RestTemplate. Sin el
    raise_for_status del service, el error de AEMPS se reenviaria con codigo
    200 y el Angular lo pintaria como un medicamento."""
    autenticar()
    cliente_http(lambda p: httpx.Response(401, text='{"error":"unauthorized"}'))

    r = await client.get("/api/cima/medicamento?nregistro=67031")

    assert r.status_code == 502


# -------------------------------------------------------------------------
# GET /api/cima/buscar
# -------------------------------------------------------------------------
async def test_buscar_devuelve_el_json_de_aemps(client, autenticar, cliente_http):
    autenticar()
    cliente_http(lambda p: httpx.Response(200, text='{"resultados":[]}'))

    r = await client.get("/api/cima/buscar?nombre=ibuprofeno")

    assert r.status_code == 200
    assert r.json() == {"resultados": []}


async def test_un_ampersand_en_el_nombre_no_cuela_parametros(client, autenticar, cliente_http):
    """El Java concatena "?nombre=" + nombre, asi que buscar
    "aspirina&pagina=99" le cambia la pagina a AEMPS. Con params= el & va
    escapado y sigue siendo parte del nombre. Es una desviacion que ARREGLA un
    fallo."""
    autenticar()
    peticiones = cliente_http(lambda p: httpx.Response(200, text="{}"))

    await client.get("/api/cima/buscar", params={"nombre": "aspirina&pagina=99"})

    params = dict(peticiones[0].url.params)
    assert params["nombre"] == "aspirina&pagina=99"
    assert params["pagina"] == "1"


async def test_el_tamanioPagina_del_cliente_no_se_reenvia(client, autenticar, cliente_http):
    """AEMPS lo ignora de todas formas (medido: con tamanioPagina=2 responde
    "tamanioPagina":200), y el endpoint no lo declara, asi que no hay manera
    de que un cliente infle la respuesta."""
    autenticar()
    peticiones = cliente_http(lambda p: httpx.Response(200, text="{}"))

    await client.get("/api/cima/buscar?nombre=ibuprofeno&tamanioPagina=5000")

    assert "tamanioPagina" not in dict(peticiones[0].url.params)


async def test_buscar_propaga_el_fallo_de_aemps_como_502(client, autenticar, cliente_http):
    autenticar()
    cliente_http(lambda p: httpx.Response(500))

    r = await client.get("/api/cima/buscar?nombre=x")

    assert r.status_code == 502


# -------------------------------------------------------------------------
# GET /api/cima/validar  (el flujo mas complejo de los 25)
# -------------------------------------------------------------------------
async def test_si_el_producto_ya_esta_en_el_inventario_da_409(client, autenticar, inventario, cliente_http):
    """Y la clave del cuerpo es "mensaje", no "error": este 409 es un
    ResponseEntity a mano del Java, no pasa por el GlobalExceptionHandler."""
    autenticar()
    inventario.return_value = [construir_articulo()]
    peticiones = cliente_http(lambda p: httpx.Response(200, text="{}"))

    r = await client.get("/api/cima/validar?nombre=ibuprofeno")

    assert r.status_code == 409
    assert r.json() == {"mensaje": "El producto ya existe en el inventario"}
    # Corta antes de salir a internet: ni AEMPS ni la IA (que cuesta dinero).
    assert peticiones == []


async def test_si_aemps_no_encuentra_nada_da_404(client, autenticar, inventario, cliente_http):
    autenticar()
    cliente_http(lambda p: httpx.Response(200, json={"resultados": []}))

    r = await client.get("/api/cima/validar?nombre=noexiste")

    assert r.status_code == 404
    assert r.json() == {"mensaje": "No se encontraron resultados en AEMPS"}


async def test_camino_feliz_devuelve_lo_que_responde_la_ia(client, autenticar, inventario, cliente_http):
    autenticar()

    def responder(peticion):
        if es_ia(peticion):
            return httpx.Response(200, json={"match": True, "nregistro": "67031"})
        return httpx.Response(200, json={"resultados": [{"nregistro": "67031", "nombre": "IBUPROFENO"}]})

    cliente_http(responder)

    r = await client.get("/api/cima/validar?nombre=ibuprofeno")

    assert r.status_code == 200
    assert r.json() == {"match": True, "nregistro": "67031"}


async def test_la_busqueda_para_la_ia_pide_tamanioPagina_100(client, autenticar, inventario, cliente_http):
    autenticar()

    def responder(peticion):
        if es_ia(peticion):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"resultados": [{"nregistro": "1", "nombre": "X"}]})

    peticiones = cliente_http(responder)

    await client.get("/api/cima/validar?nombre=ibuprofeno")

    a_aemps = [p for p in peticiones if not es_ia(p)][0]
    assert dict(a_aemps.url.params)["tamanioPagina"] == "100"


async def test_la_llamada_a_la_ia_lleva_la_api_key(client, autenticar, inventario, cliente_http):
    autenticar()

    def responder(peticion):
        if es_ia(peticion):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"resultados": [{"nregistro": "1", "nombre": "X"}]})

    peticiones = cliente_http(responder)

    await client.get("/api/cima/validar?nombre=ibuprofeno")

    a_ia = [p for p in peticiones if es_ia(p)][0]
    assert a_ia.headers["x-api-key"] == settings.ia_service_api_key


async def test_el_camino_feliz_registra_IA_MATCH_con_el_usuario_del_token(
    client, autenticar, inventario, cliente_http, log
):
    autenticar(username="farmaceutico01")

    def responder(peticion):
        if es_ia(peticion):
            return httpx.Response(200, json={"match": True})
        return httpx.Response(200, json={"resultados": [{"nregistro": "1", "nombre": "X"}]})

    cliente_http(responder)

    await client.get("/api/cima/validar?nombre=ibuprofeno")

    args = log.await_args.args
    assert args[1] == "farmaceutico01"
    assert args[2] == "IA_MATCH"
    assert args[3] == "ibuprofeno"


@pytest.mark.parametrize("respuesta_ia", [401, 500, 503])
async def test_un_fallo_de_la_ia_da_500_y_no_502(
    client, autenticar, inventario, cliente_http, respuesta_ia
):
    """LA asimetria del paso 12. El 502 es solo de AEMPS: en el Java no hay
    try alrededor de la llamada a la IA (CimaController.java:105), asi que
    cualquier fallo suyo sube al handler generico."""
    autenticar()

    def responder(peticion):
        if es_ia(peticion):
            return httpx.Response(respuesta_ia, text="lo que sea")
        return httpx.Response(200, json={"resultados": [{"nregistro": "1", "nombre": "X"}]})

    cliente_http(responder)

    r = await client.get("/api/cima/validar?nombre=ibuprofeno")

    assert r.status_code == 500
    assert r.json() == {"error": "Error interno del servidor"}


async def test_si_la_ia_esta_caida_da_500(client, autenticar, inventario, cliente_http):
    autenticar()

    def responder(peticion):
        if es_ia(peticion):
            raise httpx.ConnectError("micro apagado", request=peticion)
        return httpx.Response(200, json={"resultados": [{"nregistro": "1", "nombre": "X"}]})

    cliente_http(responder)

    r = await client.get("/api/cima/validar?nombre=ibuprofeno")

    assert r.status_code == 500


async def test_si_la_ia_falla_NO_se_escribe_el_IA_MATCH(
    client, autenticar, inventario, cliente_http, log
):
    """En el Java el log va despues de la llamada y sin try: los intentos
    fallidos no dejan rastro. Se replica. Si algun dia interesa auditarlos,
    hay que decidirlo a proposito — no es un olvido."""
    autenticar()

    def responder(peticion):
        if es_ia(peticion):
            return httpx.Response(500)
        return httpx.Response(200, json={"resultados": [{"nregistro": "1", "nombre": "X"}]})

    cliente_http(responder)

    await client.get("/api/cima/validar?nombre=ibuprofeno")

    log.assert_not_awaited()


async def test_validar_sin_el_parametro_nombre_da_422(client, autenticar, inventario, cliente_http):
    autenticar()
    cliente_http(lambda p: httpx.Response(200, json={}))

    r = await client.get("/api/cima/validar")

    assert r.status_code == 422
