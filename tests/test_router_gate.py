# tests/test_router_gate.py
#
# La version automatica de la checklist de router.py, que hasta ahora se hacia
# a mano en cada paso.
#
# Por que existe: en Spring, .anyRequest().authenticated() es un cajon de
# sastre y un @RestController nuevo nace PROTEGIDO. En FastAPI no hay cajon de
# sastre: un include_router() sin dependencies nace ABIERTO. Ese agujero
# aparecio en dos pasos seguidos — articulos en el paso 9 (PUT /updateStock
# abierto) y users en el 9 bis (GET /users/all devolviendo los 9 usuarios sin
# token).
#
# Las dos listas estan escritas a mano a proposito: son el contrato con el
# Angular. Si un endpoint cambia de ruta, de metodo o de gate, el test se pone
# rojo y hay que venir aqui a decidirlo, que es justo lo que se quiere.
#
# Comprobado que el test NO es decorativo: montando una app con el cima_router
# incluido SIN dependencies, test_ninguna_ruta_protegida_se_queda_abierta
# falla (aparecen GET /api/cima/medicamento y /buscar sin security) y el 401
# de /buscar pasa a ser un 500.
import pytest

from app.main import app

METODOS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# permitAll() del SecurityConfig. Nada mas puede estar aqui.
PUBLICAS = {
    ("GET", "/"),              # el health que no existe en el Java
    ("POST", "/auth/login"),   # el huevo y la gallina: sin esto no hay token
}

# Las 24 restantes. /activity-log/all ademas exige SUPERADMIN, pero eso se
# prueba en su propio fichero: aqui solo se mira que no este abierta.
PROTEGIDAS = {
    ("GET", "/auth/protected"),
    ("GET", "/articulos/All"),
    ("POST", "/articulos/insert"),
    ("GET", "/articulos/search/{keyword}"),
    ("PUT", "/articulos/updateItem"),
    ("PUT", "/articulos/updateStock"),
    ("DELETE", "/articulos/{id}"),
    ("PATCH", "/articulos/{id}/aemps"),
    ("GET", "/users/all"),
    ("GET", "/users/{username}"),
    ("POST", "/users/insert"),
    ("PUT", "/users/update"),
    ("DELETE", "/users/{id}"),
    ("GET", "/ventas/all"),
    ("GET", "/ventas/{username}"),
    ("POST", "/ventas/registrar"),
    ("POST", "/ventas/registrar/list"),
    ("DELETE", "/ventas/cancelar/{id}"),
    ("GET", "/cancelaciones"),
    ("POST", "/cancelaciones"),
    ("GET", "/activity-log/all"),
    ("GET", "/api/cima/medicamento"),
    ("GET", "/api/cima/buscar"),
    ("GET", "/api/cima/validar"),
}


def operaciones() -> set[tuple[str, str]]:
    """Las operaciones realmente registradas, leidas del OpenAPI.

    NO se usa app.routes: en FastAPI 0.141.1 no aplana los routers incluidos
    (medido: 6 entradas, las de /docs + / + un _IncludedRouter), asi que
    introspeccionarlo parece decir que no hay ninguna ruta.
    """
    paths = app.openapi()["paths"]
    return {
        (metodo.upper(), ruta)
        for ruta, ops in paths.items()
        for metodo in ops
        if metodo.upper() in METODOS
    }


def test_inventario_de_rutas():
    # Ni una de menos (un include_router olvidado: el fichero esta escrito y
    # los endpoints no existen, con un 404 y ninguna pista) ni una de mas.
    assert operaciones() == PUBLICAS | PROTEGIDAS


def test_ninguna_ruta_protegida_se_queda_abierta():
    # Estructural, sin lanzar peticiones: FastAPI declara "security" en la
    # operacion cuando la ruta depende de oauth2_scheme, sea por el
    # include_router o por un parametro del endpoint. Es lo mismo que pinta el
    # candado en /docs.
    paths = app.openapi()["paths"]
    abiertas = {
        (metodo.upper(), ruta)
        for ruta, ops in paths.items()
        for metodo, op in ops.items()
        if metodo.upper() in METODOS and "security" not in op
    }
    assert abiertas == PUBLICAS


@pytest.mark.parametrize("metodo,ruta", sorted(PROTEGIDAS))
async def test_sin_token_da_401(client, metodo, ruta):
    """Lo mismo, pero de verdad: 24 peticiones sin cabecera Authorization.

    El equivalente de un @ParameterizedTest. El test de arriba lee el
    documento; este ejecuta, y hacen falta los dos: el OpenAPI podria declarar
    el candado y la dependencia no cortar.

    Los {parametros} se rellenan con "1": el 401 salta al resolver las
    dependencias, antes de validar la ruta, el query y el cuerpo. Por eso
    POST /articulos/insert da 401 y no 422 aunque vaya sin body.
    """
    url = ruta
    while "{" in url:
        inicio = url.index("{")
        fin = url.index("}")
        url = url[:inicio] + "1" + url[fin + 1:]

    r = await client.request(metodo, url)
    assert r.status_code == 401, f"{metodo} {url} -> {r.status_code}"
