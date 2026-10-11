# tests/test_health.py
#
# OJO con lo que se esta probando aqui: GET / NO existe en el backend Java.
# Comprobado al escribir estos tests: no hay HealthController, no hay
# spring-boot-starter-actuator en el pom.xml y ninguno de los 7 controladores
# mapea "/". Es un anadido del espejo, asi que estos tests verifican el
# contrato que la API se ha dado a si misma, no una replica.
from app.main import app


async def test_raiz_responde_ok(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "message": "EasyFarma API migrada a FastAPI funcionando",
    }


async def test_la_raiz_no_pide_token(client):
    # Sin cabecera Authorization. Si algun dia / cayera dentro de un gate, se
    # romperian el healthcheck del contenedor y el arranque en el VPS.
    r = await client.get("/")
    assert r.status_code == 200


def test_el_openapi_se_genera():
    # Un test SINCRONO a proposito: app.openapi() no es async. Si un cambio
    # dejara un response_model imposible de serializar, revienta aqui y no al
    # abrir /docs en el navegador.
    esquema = app.openapi()
    assert esquema["info"]["title"] == "EasyFarma API"
    assert esquema["info"]["version"] == "1.0.0"


def test_el_authorize_de_swagger_pide_un_token_y_no_un_formulario():
    """El boton "Authorize" de /docs tiene que ser una caja para pegar el JWT,
    igual que en el Swagger del backend Java.

    ANTES era OAuth2PasswordBearer, que pintaba el formulario del flujo OAuth2
    (usuario, contrasena, client_id, client_secret) y NO funcionaba: ese
    formulario envia los datos como formulario y /auth/login espera JSON.
    Medido contra el contenedor: form -> 422, JSON -> 401/200. El candado
    estaba pintado y no habia forma de sacar el token por ahi.

    Este test existe para que no se vuelva atras sin darse cuenta: es lo unico
    del contrato que no se nota hasta abrir el navegador."""
    esquema = app.openapi()
    esquemas = esquema["components"]["securitySchemes"]

    assert "HTTPBearer" in esquemas
    assert esquemas["HTTPBearer"] == {"type": "http", "scheme": "bearer"}
    # Y que no quede rastro del flujo viejo.
    assert "OAuth2PasswordBearer" not in esquemas
