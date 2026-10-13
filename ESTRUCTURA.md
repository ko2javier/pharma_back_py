# EasyFarma API — Migración de Spring Boot a FastAPI

Documento de referencia de la estructura del proyecto. Réplica funcional del backend
`farmacia-ko2-back` (Spring Boot 3 / Java 21) sobre **FastAPI + async**.

- **Proyecto origen:** `/home/jabier/Documentos/backup/farmacia-ko2-back` (rama `master`)
- **Proyecto destino:** `/home/jabier/Documentos/backup/farmacia-ko2-back_fastApi`
- **Python:** 3.12.3
- **Fecha:** 2026-09-01

---

## 1. Decisión de arquitectura: todo async

Se construye **async de principio a fin**. Motivos:

- FastAPI está diseñado async-first; es el idioma dominante en su ecosistema.
- SQLAlchemy 2.0 tiene soporte async maduro y estable.
- Es lo que más valor aporta de cara al mercado laboral.

**Matiz honesto:** no todas las empresas Python trabajan async. Django (síncrono) sigue
teniendo más cuota de mercado, y hay mucho FastAPI en producción con SQLAlchemy síncrono.
Async es *una* opción profesional válida y la más idiomática para FastAPI, no la única.

### Regla de oro del async (leer antes de escribir código)

> Una sola llamada **bloqueante** dentro de un `async def` congela el *event loop* entero
> y degrada el rendimiento de **toda** la aplicación, no solo de esa petición.

Prohibido dentro de un `async def`:

| Nunca (bloquea) | Usar en su lugar |
|---|---|
| `requests.get(...)` | `await httpx.AsyncClient().get(...)` |
| `time.sleep(n)` | `await asyncio.sleep(n)` |
| `session.query(...)` síncrona | `await session.execute(select(...))` |
| `open()` / lectura de ficheros | `aiofiles` |
| `bcrypt.hashpw(...)` (usa CPU, ~100 ms) | `await asyncio.to_thread(bcrypt.hashpw, ...)` |

Si una librería no tiene versión async, se envuelve con `await asyncio.to_thread(fn, args)`.

### Nota sobre el pool de conexiones

La base de datos en Aiven está limitada (en Spring: `hikari.maximum-pool-size=3`).
Con async es fácil abrir muchas conexiones a la vez, así que hay que **limitar el pool
explícitamente** en el engine:

```python
create_async_engine(url, pool_size=3, max_overflow=0, pool_pre_ping=True)
```

---

## 2. Stack elegido

| Necesidad | Librería | Equivalente en Spring |
|---|---|---|
| Framework web | `fastapi` | `spring-boot-starter-web` |
| Servidor ASGI | `uvicorn[standard]` | Tomcat embebido |
| ORM async | `sqlalchemy[asyncio]` 2.x | Hibernate / Spring Data JPA |
| Driver MySQL async | `aiomysql` | `mysql-connector-j` |
| Configuración | `pydantic-settings` | `application.properties` + `@Value` |
| Validación / DTOs | `pydantic` v2 | DTOs + Jackson |
| JWT | `pyjwt` | `jjwt` |
| Hash de contraseñas | `bcrypt` | `BCryptPasswordEncoder` |
| HTTP client async | `httpx` | `RestTemplate` |
| Migraciones (opcional) | `alembic` | (no había; `ddl-auto=none`) |
| Tests | `pytest`, `pytest-asyncio`, `httpx` | JUnit + `spring-security-test` |
| Multipart / formularios | `python-multipart` | — |

**Compatibilidad de contraseñas:** Spring Security genera hashes BCrypt con prefijo `$2a$`.
La librería `bcrypt` de Python los verifica sin problema, así que **los usuarios existentes
en la base de datos seguirán pudiendo entrar**. No hay que migrar contraseñas.

> Nota: se usa `bcrypt` directamente y no `passlib`, que lleva sin publicar versión desde
> 2020 y da problemas de compatibilidad con bcrypt 4.x.

---

## 3. Estructura de carpetas

```
farmacia-ko2-back_fastApi/
│
├── app/                              # Todo el código de la aplicación
│   ├── __init__.py
│   ├── main.py                       ← FpApplication.java + CORS de SecurityConfig
│   │
│   ├── core/                         ← paquete config/
│   │   ├── __init__.py
│   │   ├── config.py                 ← application.properties (pydantic-settings)
│   │   ├── database.py               ← DataSource + Hikari (async engine, sessionmaker)
│   │   └── security.py               ← JwtUtil.java (crear/validar JWT, hash bcrypt)
│   │
│   ├── models/                               ← paquete model/, solo las @Entity (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── base.py                           ← DeclarativeBase común
│   │   ├── user_model.py                     ← Users.java              → tabla users
│   │   ├── authority_model.py                ← Authorities.java        → tabla authorities
│   │   ├── articulo_model.py                 ← Articulos.java          → tabla articulos
│   │   ├── venta_model.py                    ← Ventas.java             → tabla ventas
│   │   ├── venta_cancelada_model.py          ← VentaCancelada.java     → tabla ventas_canceladas
│   │   │                                       (+ enum CancellationStatus)
│   │   └── activity_log_model.py             ← ActivityLog.java        → tabla activity_log
│   │
│   ├── schemas/                              ← los *_DTO.java (Pydantic, entrada/salida)
│   │   ├── __init__.py
│   │   ├── auth_schema.py                    ← credenciales de login + respuesta {token}
│   │   ├── user_schema.py                    ← Insert_User_DTO.java + UserOut (sin password)
│   │   ├── articulo_schema.py                ← Insert_DTO.java + UpdateDTO.java
│   │   ├── venta_schema.py                   ← VentaDTO.java
│   │   ├── venta_cancelada_schema.py         ← entrada/salida de cancelaciones
│   │   ├── activity_log_schema.py            ← salida del historial
│   │   └── ia_schema.py                      ← MatchRequestDTO + MedicamentoAempsDTO
│   │
│   ├── repositories/                         ← paquete repository/ (acceso a datos, sin lógica)
│   │   ├── __init__.py
│   │   ├── user_repository.py                ← UserRepository + AuthoritiesRepository
│   │   ├── articulo_repository.py            ← ArticulosRepository
│   │   ├── venta_repository.py               ← VentasRepository
│   │   ├── venta_cancelada_repository.py
│   │   └── activity_log_repository.py
│   │
│   ├── services/                             ← paquete service/ (lógica de negocio)
│   │   ├── __init__.py
│   │   ├── user_service.py                   ← UserService.java
│   │   ├── articulo_service.py               ← ArticuloService.java
│   │   ├── venta_service.py                  ← VentaService.java (transacciones)
│   │   ├── venta_cancelada_service.py
│   │   ├── activity_log_service.py           ← ActivityLogService.java
│   │   ├── cima_service.py                   ← lógica AEMPS que hoy vive en CimaController
│   │   └── ia_service.py                     ← IaService.java (httpx async + x-api-key)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                           ← JwtAuthenticationFilter + @PreAuthorize
│   │   │                                       get_db / get_current_user / require_role
│   │   └── routes/                           ← paquete controller/
│   │       ├── __init__.py
│   │       ├── router.py                     ← agrupa todos los routers y los monta
│   │       ├── auth_controller.py            ← AuthController           → /auth
│   │       ├── user_controller.py            ← UserController           → /users
│   │       ├── articulo_controller.py        ← ArticuloController       → /articulos
│   │       ├── venta_controller.py           ← VentaController          → /ventas
│   │       ├── venta_cancelada_controller.py ← VentaCanceladaController → /cancelaciones
│   │       ├── activity_log_controller.py    ← ActivityLogController    → /activity-log
│   │       └── cima_controller.py            ← CimaController           → /api/cima
│   │
│   └── exceptions/                   ← paquete exception/
│       ├── __init__.py
│       ├── custom.py                 ← 4 excepciones (ver §8 bis), no las 2 del Java
│       └── handlers.py               ← GlobalExceptionHandler (app.add_exception_handler)
│
├── tests/                            ← src/test/java/
│   ├── __init__.py
│   ├── conftest.py                   ← fixtures: cliente async, BD de prueba
│   ├── test_auth_controller.py       ← AuthControllerTest.java
│   └── test_health.py                ← FpApplicationTests.java (contexto arranca)
│
├── alembic/                          # Opcional — el esquema ya existe en Aiven
│   ├── versions/
│   └── env.py
├── alembic.ini
│
├── .venv/                            # Entorno virtual (NO se sube a git)
├── .env                              # Secretos reales (NO se sube a git)
├── .env.example                      # Plantilla con las claves vacías (sí se sube)
├── .gitignore
├── requirements.txt                  ← pom.xml
├── Dockerfile                        ← Dockerfile (multistage)
├── docker-compose.yml                ← docker-compose.yml
├── .github/workflows/deploy.yml      ← mismo workflow de deploy
└── README.md
```

### Por qué esta estructura

Es la disposición estándar de un proyecto FastAPI mediano-grande (la que recomienda la
documentación oficial en "Bigger Applications" y la que popularizó la plantilla
`full-stack-fastapi-template`), y además mantiene **la misma separación por capas que ya
tienes en Java**, para que la traducción sea fichero a fichero:

```
controller  →  api/routes      (HTTP: recibe, valida, responde)
service     →  services        (lógica de negocio, transacciones)
repository  →  repositories    (consultas a la BD)
model       →  models          (tablas) + schemas (DTOs)
config      →  core            (arranque, seguridad, conexión)
exception   →  exceptions      (errores propios y su traducción a HTTP)
```

La única diferencia real de criterio es que en Python se **separa la tabla del DTO** en
dos carpetas (`models/` vs `schemas/`), mientras que en tu proyecto Java conviven las dos
cosas en el paquete `model/`. Esa separación es obligatoria aquí: las tablas son
SQLAlchemy y los DTOs son Pydantic, son dos librerías distintas.

### Convención de nombres: sufijo explícito en todos los ficheros

**Regla única: cada fichero lleva el sufijo de su capa.** Una clase Java se traduce a un
fichero Python con el mismo nombre en `snake_case`:

| Java | Python |
|---|---|
| `UserController.java` | `api/routes/user_controller.py` |
| `UserService.java` | `services/user_service.py` |
| `UserRepository.java` | `repositories/user_repository.py` |
| `Users.java` (`@Entity`) | `models/user_model.py` |
| `Insert_User_DTO.java` | `schemas/user_schema.py` |

Sí, el sufijo repite lo que ya dice la carpeta (`models/user_model.py`). Es redundante a
propósito: con la convención "corta" tendrías **tres ficheros llamados `user.py`** abiertos
a la vez en el editor y la pestaña no te diría cuál es cuál. El nombre completo elimina esa
ambigüedad en las pestañas, en los buscadores (`Ctrl+Mayús+N`), en los *stack traces* y en
los mensajes de error de importación.

> **Matiz honesto:** la convención más extendida en el ecosistema FastAPI es la corta
> (`api/routes/users.py`, `schemas/user.py`), apoyándose en que el paquete ya da el
> contexto: `from app.schemas import user`. Es igual de válida y la verás en la plantilla
> oficial `full-stack-fastapi-template`. Aquí se elige la explícita porque este proyecto
> es además un ejercicio de aprendizaje y porque `repositories/` y `services/` ya la usaban
> de forma natural. Lo importante es no mezclar las dos.

Y por lo mismo, al importar se nombra el módulo completo, nunca se abrevia:

```python
from app.models.user_model import Users          # la tabla (SQLAlchemy)
from app.schemas.user_schema import UserOut      # el DTO (Pydantic)
```

Excepciones a la regla, porque no tienen capa que desambiguar: `base.py`, `router.py`,
`deps.py`, `__init__.py` y todo lo de `core/` (`config.py`, `database.py`, `security.py`)
y `exceptions/` (`custom.py`, `handlers.py`).

---

## 4. Equivalencias conceptuales (no es traducción literal)

| Spring Boot | FastAPI | Comentario |
|---|---|---|
| `SwaggerConfig.java` | *(no existe)* | FastAPI genera `/docs` y `/openapi.json` solo. **Fichero eliminado.** |
| `JwtAuthenticationFilter` | `api/deps.py` | Deja de ser un filtro global: es una *dependencia* que se inyecta por router. |
| `@PreAuthorize` / `hasRole` | `Depends(require_role("SUPERADMIN"))` | Aquí encaja la jerarquía de roles y elimina los `if` repetidos del `UserController`. |
| `JdbcUserDetailsManager` | `user_repository` | Las dos consultas SQL del `SecurityConfig` pasan a ser consultas normales. |
| `@Transactional` | `async with session.begin():` | Imprescindible en `cancelar_venta`: devuelve stock y escribe en dos tablas. |
| `@Version` (bloqueo optimista) | `__mapper_args__ = {"version_id_col": version}` | SQLAlchemy lo soporta igual que Hibernate. |
| `RestTemplate` | `httpx.AsyncClient` | Para AEMPS y el microservicio de IA. |
| `@Autowired` | `Depends(...)` | Inyección de dependencias nativa de FastAPI. |
| `ResponseEntity.status(...)` | `raise HTTPException(...)` | O `Response(status_code=...)` cuando haga falta el cuerpo. |
| `application-dev.properties` | `.env` + `ENVIRONMENT=dev` | Un solo `config.py` que lee del entorno. |
| `SecurityContextHolder.getContext()` | `current_user: Users = Depends(get_current_user)` | El usuario autenticado se recibe como parámetro, no desde un contexto global. |

---

## 5. Endpoints a replicar

| Método | Ruta | Rol requerido | Origen |
|---|---|---|---|
| POST | `/auth/login` | público | `AuthController` |
| GET | `/auth/protected` | autenticado | `AuthController` |
| GET | `/users/all` | autenticado | `UserController` |
| GET | `/users/{username}` | autenticado | `UserController` |
| POST | `/users/insert` | ADMIN solo puede crear SELLER; un SELLER no entra — **ver nota** | `UserController` |
| PUT | `/users/update` | ADMIN no puede tocar ADMIN/SUPERADMIN; un SELLER no entra | `UserController` |
| DELETE | `/users/{id}` | ADMIN no puede borrar ADMIN/SUPERADMIN; un SELLER no entra | `UserController` — **borrado lógico, ver nota** |
| GET | `/articulos/All` | autenticado | `ArticuloController` |
| GET | `/articulos/search/{keyword}` | autenticado | `ArticuloController` |
| POST | `/articulos/insert` | autenticado | `ArticuloController` |
| PUT | `/articulos/updateStock` | autenticado (lote) | `ArticuloController` |
| PUT | `/articulos/updateItem` | autenticado | `ArticuloController` |
| PATCH | `/articulos/{id}/aemps` | autenticado | `ArticuloController` |
| DELETE | `/articulos/{id}` | autenticado | `ArticuloController` |
| GET | `/ventas/all` | autenticado | `VentaController` |
| GET | `/ventas/{username}` | autenticado | `VentaController` |
| POST | `/ventas/registrar` | autenticado | `VentaController` |
| POST | `/ventas/registrar/list` | autenticado (lote) | `VentaController` |
| DELETE | `/ventas/cancelar/{id}?responsable=` | autenticado | `VentaController` |
| GET | `/cancelaciones` | autenticado | `VentaCanceladaController` |
| POST | `/cancelaciones` | autenticado | `VentaCanceladaController` |
| GET | `/activity-log/all` | **SUPERADMIN** | `ActivityLogController` |
| GET | `/api/cima/medicamento?nregistro=` | autenticado | `CimaController` |
| GET | `/api/cima/buscar` | autenticado | `CimaController` |
| GET | `/api/cima/validar?nombre=` | autenticado | `CimaController` |

### Nota sobre `DELETE /users/{id}`: borrado lógico, no físico

**Desviación deliberada respecto al Java.** `UserController.java` borra la fila de
verdad. Aquí no: `users` tiene dos claves foráneas con `ON DELETE CASCADE` hacia
`authorities.username` y `ventas.id_username` (comprobado contra el
`information_schema` real de Aiven), así que un `DELETE` físico se llevaría por
delante **todo el historial de ventas** del usuario sin avisar. Se descubrió
probando el borrado contra la base de datos real.

`UserService.delete_user_by_id` pone `enabled=False` en vez de borrar la fila.
Con eso:
- el usuario deja de poder autenticarse (`authenticate_user` comprueba `enabled`
  después de la contraseña, no antes, para no filtrar por *timing* si la cuenta
  existe pero está deshabilitada),
- sus ventas y su rastro en `activity_log` quedan intactos,
- la fila de `authorities` **no se toca**: la comparte el backend Java, y su
  propio login también debe seguir respetando `enabled=False`.

`UserRepository.delete` (el `DELETE` físico) se deja en el repositorio como
equivalente genérico de `JpaRepository.delete`, pero el `service` ya no lo llama.

### Nota sobre el SELLER en `/users`: endurecido respecto al Java

**Desviación deliberada, decidida el 2026-10-01.** En el Java, un SELLER con un token
válido puede llamar a `POST /users/insert` y crearse un SUPERADMIN: `UserController` sólo
comprueba `"ADMIN".equals(rolCaller)`, y en todo el backend hay **un único** control de rol
(`SecurityConfig:64`, `/activity-log/**` → `hasRole("SUPERADMIN")`; no existe ni un
`@PreAuthorize`). La restricción del SELLER vive sólo en el Angular:
`home.component.html:57` esconde "Gestión Usuarios" con `*ngIf="userRole!='SELLER'"`.
Esconder el botón no protege el endpoint — basta un `curl` con el token de un vendedor.

Aquí los **tres endpoints que escriben** (`/insert`, `/update`, `DELETE /{id}`) devuelven
**403** a un SELLER y registran antes un `FORBIDDEN_ACTION`, igual que las otras tres
reglas. Los dos `GET` se quedan como en el Java (autenticado a secas). No rompe al
frontend, que nunca ofrece esa pantalla a un SELLER. Comprobado ejecutando: antes del
cambio un SELLER pidiendo crear un SUPERADMIN recibía **409** (el duplicado del service),
es decir, la regla no lo frenaba; ahora recibe 403 y queda en el log.

Está en `user_controller.py` y no en `require_role("ADMIN", "SUPERADMIN")` —que sería lo
idiomático— porque el `FORBIDDEN_ACTION` es parte de la regla: `require_role` corta sin
dejar rastro, y un SELLER tocando `/users` es justo lo que interesa ver en el log.

### Flujo de `/api/cima/validar` (el más complejo)

1. Si el producto ya existe en inventario → `409 Conflict`, cuerpo `{"mensaje": ...}`.
2. Consulta a AEMPS (`https://cima.aemps.es/cima/rest/medicamentos`) con `tamanioPagina=100`.
3. Convierte los resultados crudos a `MedicamentoAempsDTO` (`nregistro` → `id`, `nombre`).
4. Si no hay resultados → `404 Not Found`, cuerpo `{"mensaje": ...}`.
5. Envía la lista al microservicio de IA (`POST {IA_SERVICE_URL}/api/v1/ia/match`, cabecera `x-api-key`).
6. Registra la búsqueda en `activity_log` con la acción `IA_MATCH` y la IP.
7. Devuelve el resultado de la IA tal cual, sin envolver.

**El 409 y el 404 llevan la clave `mensaje`, no `error`:** en el Java son `ResponseEntity`
escritos a mano y no pasan por el `GlobalExceptionHandler`. Por eso en Python son
`JSONResponse` a mano y **se borró `AempsNotFoundException`** (ver §8 bis).

**Si falla la IA, son 500 y no 502.** Es lo más importante de este flujo y lo contrario de lo
que decía este documento: no hay ningún `try` alrededor de la llamada a la IA
(`CimaController.java:105`, ni dentro de `IaService.java`), así que una caída, un timeout, una
api-key mala o un 5xx del micro suben sin capturar hasta el handler genérico. El 502 es sólo de
AEMPS. Se replica tal cual, y por eso `ia_service.py` no tiene `try`.

**Tampoco queda rastro de los intentos fallidos:** el `IA_MATCH` del paso 6 sólo se escribe si
la IA respondió bien, porque en el Java está después de la llamada y sin `try`.

Lo que se descubrió al escribirlo (2026-10-11), midiendo contra AEMPS de verdad:

- **"Hasta 100 resultados" es falso.** AEMPS **ignora** `tamanioPagina` y devuelve páginas de
  200 (`tamanioPagina=2` → `"tamanioPagina":200` en la respuesta). Se manda igual por fidelidad.
- **Con un `nregistro` inexistente AEMPS da `204` con cuerpo vacío**, no un JSON de error. Por
  eso `/medicamento` devuelve el **texto crudo** y no `response.json()`: parsearlo sería
  `ValueError` → 502, cuando el Java devuelve 200 vacío.
- **`"resultados": null`** haría `NullPointerException` → 500 en el Java. Aquí se trata como
  lista vacía → 404, que es lo que significa.

Desviaciones deliberadas del paso 12:

| Desviación | Por qué |
|---|---|
| Parámetros en `params=`, no concatenados en la URL | El Java hace `"?nombre=" + nombre`: un `&` en el nombre cuela parámetros en la petición a AEMPS |
| Timeout de 10 s (AEMPS) y 30 s (IA) | El Java **no tiene ninguno** (`new RestTemplate()` sin configurar, comprobado: ni `RestTemplateBuilder` ni `setReadTimeout` en todo el proyecto). En async una llamada colgada deja la conexión abierta para siempre |
| Un `httpx.AsyncClient` compartido (lifespan de `main.py`) | El Java crea uno por llamada y no reutiliza conexiones. El sitio correcto allí habría sido un `@Bean` en una `@Configuration` |
| Falta un query param → 422 | El Java da 400 (es Pydantic, igual que en el resto del proyecto) |

**`tamanioPagina` NO se declara en `/buscar`**, aunque el Angular lo manda
(`cima.service.ts:18`): el Java tampoco lo declara y Spring lo descarta. Declararlo cambiaría
lo que ve el catálogo en producción.

---

## 6. Variables de entorno (`.env`)

Las mismas que ya usa el backend Java, para poder apuntar a la misma base de datos:

```
# OJO: 8001, no 8000. En local el microservicio de IA ya ocupa el 8000, y con
# PORT=8000 la variable IA_SERVICE_URL apuntaría a esta propia API.
PORT=8001

JWT_SECRET=

# La conexión va por piezas, no como una URL entera (ver más abajo).
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=

IA_SERVICE_URL=
IA_SERVICE_API_KEY=

ENVIRONMENT=dev

# Opcional: ruta del ca.pem de Aiven. Por defecto, ca.pem en la raíz.
# AIVEN_CA_PATH=ca.pem
```

**Por qué las cinco piezas y no un `DB_URL`.** Una URL de SQLAlchemy lleva usuario y
contraseña dentro (`mysql+aiomysql://usuario:clave@host:puerto/bd`), así que tener además
`DB_USER` y `DB_PASSWORD` sueltos —como hacía el Java, donde JDBC los necesitaba aparte—
deja el mismo secreto en dos sitios. Guardando las piezas, `core/config.py` compone la URL
en la propiedad `database_url` y cada secreto se rota por su cuenta. Además, una contraseña
con `@`, `:`, `/` o `#` rompería la URL si no va percent-encoded: al componerla en código se
escapa una sola vez con `quote_plus()` y de forma fiable.

**Ojo con el formato respecto a Java.** Spring usa `jdbc:mysql://host:puerto/bd`; SQLAlchemy
necesita `mysql+aiomysql://usuario:clave@host:puerto/bd`. Aiven además exige SSL, que no va
en la URL sino aparte, en el `connect_args` del engine (`core/database.py`).

**El `ca.pem` de Aiven es obligatorio.** Aiven firma el certificado del servidor con una CA
propia, así que `ssl.create_default_context()` a secas falla con
`CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain`. Se descarga de la
consola de Aiven y se le pasa al contexto con `cafile=`, de modo que la conexión queda con
`verify_mode=CERT_REQUIRED` y `check_hostname=True`. El fichero no es un secreto — es el
certificado público de la CA — y va versionado en la raíz del repositorio; su ruta se
declara en `Settings.aiven_ca_path`, no escrita a mano en `database.py`.

Esto es **más estricto que el backend Java**, que apunta a la misma base de datos con
`verifyServerCertificate=false`: cifra, pero no comprueba con quién habla.

**El bucle de eventos importa en Windows.** uvicorn 0.36+ elige el bucle con una factoría, y
en Windows la de por defecto es `ProactorEventLoop`, que no soporta el paso a TLS a mitad de
conexión que exige el protocolo MySQL: la conexión a Aiven muere con un
`OperationalError (2003)` cuya causa real es un `OSError [WinError 87]`. Por eso el bloque
`if __name__ == "__main__"` de `main.py` arranca uvicorn con
`loop="asyncio:SelectorEventLoop"`, y por eso esa línea **no lleva comprobación de
plataforma**: `SelectorEventLoop` existe también en Linux, donde ya es el bucle por defecto
(epoll). Arrancando por la línea de órdenes hace falta el mismo parámetro
(`--loop asyncio:SelectorEventLoop`); `--reload` también vale, porque uvicorn usa subproceso
y entonces elige el selector por su cuenta.

Un aviso para depurar: el Proactor **oculta la causa real** de los fallos de handshake. El
error de certificado de más arriba aparecía como `WinError 87` hasta que se repitió la
prueba con el selector.

---

## 6 bis. El token JWT (contrato con el frontend)

Extraído de `JwtUtil.java` y `AuthController.java`. El frontend en producción **lee el rol
del propio token**, así que estos claims no se pueden cambiar:

| Claim | Valor |
|---|---|
| `sub` | el `username` |
| `role` | `users.permiso` **tal cual, sin el prefijo `ROLE_`** — `"SUPERADMIN"`, no `"ROLE_SUPERADMIN"` |
| `iat` | fecha de emisión |
| `exp` | +10 horas |

Algoritmo HS256 con `JWT_SECRET` en bytes crudos. Ojo con el `role`: Spring SÍ antepone
`ROLE_` al construir las *authorities* (`CONCAT('ROLE_', permiso)` en el `JdbcUserDetailsManager`),
pero dentro del token va el valor crudo. Si `deps.py` compara contra `ROLE_SUPERADMIN`, nadie
entrará en `/activity-log`.

Las contraseñas de Aiven son `$2a$10$` (BCryptPasswordEncoder, 10 rondas) y se validan sin
migrar nada. Los hashes nuevos se generan con `bcrypt.gensalt(rounds=10, prefix=b"2a")`: el
defecto de la librería Python es `$2b$` con 12 rondas, que es compatible pero cuesta 198 ms en
vez de 50 y dejaría la tabla `users` con dos costes mezclados.

**bcrypt va siempre en `asyncio.to_thread`.** Medido con cuatro hashes seguidos: la llamada
directa para el bucle de eventos 821 ms —la API entera, no sólo quien hace login— y con
`to_thread` baja a 22 ms. En Spring no pasaba porque cada petición tenía su hilo de Tomcat.

**Pendiente de decidir:** `JWT_SECRET` tiene 13 bytes y PyJWT avisa en cada firma
(`InsecureKeyLengthWarning`, el mínimo recomendado para HS256 son 32). Rotarlo obliga a
hacerlo **a la vez en el backend Java**, que comparte el secreto y está en producción.

---

## 7. Orden de construcción

Se construye de dentro hacia fuera: primero lo que no depende de nada.

| Paso | Qué se hace | Ficheros |
|---|---|---|
| 1 | Esqueleto, dependencias y arranque | `requirements.txt`, `app/main.py`, `.env` |
| 2 | Configuración y conexión a BD | `core/config.py`, `core/database.py` |
| 3 | Tablas | `models/*_model.py` |
| 4 | DTOs | `schemas/*_schema.py` |
| 5 | Seguridad: JWT + bcrypt | `core/security.py` |
| 6 | Login funcionando | `repositories/user_repository.py`, `services/user_service.py`, `api/routes/auth_controller.py` |
| 7 | Dependencias de autenticación y roles | `api/deps.py` |
| 8 | Errores propios | `exceptions/*` |
| 9 | CRUD de artículos | `repositories` + `services` + `routes` de artículos |
| **9 bis** | **CRUD de usuarios — hueco del plan original**, ver §10 | `api/routes/user_controller.py` (el repo y el service ya existen del paso 6) |
| 10 | Ventas y cancelaciones (transacciones) | íd. ventas |
| 11 | Activity log | íd. activity log |
| 12 | AEMPS + microservicio IA | `cima_service.py`, `ia_service.py`, `routes/cima_controller.py` |
| 13 | Tests | `tests/*` |
| ~~14~~ | ~~Docker y despliegue~~ — **hecho el 2026-10-12**, desplegado en AWS (§11) | — |

---

## 8. Estado actual

*Actualizado el 2026-10-11.*

| Paso | Qué | Estado |
|---|---|---|
| 1 | Esqueleto, dependencias y arranque | Hecho y verificado |
| 2 | `core/config.py` + `core/database.py` | Hecho y verificado contra Aiven (`SELECT 1`, TLS con el `ca.pem`, `get_db()`) |
| 3 | `models/` — 6 entidades + `base.py` | Hecho y verificado |
| 4 | `schemas/` — 7 ficheros, 14 clases Pydantic | Hecho y verificado |
| 5 | `core/security.py` — JWT + bcrypt | Hecho y verificado (claims, caducidad, hash `$2a$10$`, rechazo de token manipulado / caducado / `alg=none`) |
| 6 | Login completo: `user_repository.py`, `activity_log_repository.py`, `user_service.py`, `activity_log_service.py`, `auth_controller.py` | Hecho y verificado contra Aiven (`/auth/login` real desde `/docs`) |
| 7 | `api/deps.py` — `get_db`, `get_current_user`, `require_role(*roles)` | Hecho y verificado (`/auth/protected` exige token válido, rechaza ausente/manipulado con 401) |
| 8 | `exceptions/custom.py` + `exceptions/handlers.py`, registrados en `main.py` | Hecho y verificado (6 excepciones → 404/404/409/409/502/500, y siguen saliendo el 200 de `/` y el 401 de `/auth/protected`) |
| 9 | Artículos: `articulo_repository.py`, `articulo_service.py`, `articulo_controller.py` + alta en `router.py` | Hecho y verificado (20 comprobaciones: 7 rutas en el OpenAPI, las 7 dan 401 sin token, y 6 casos de excepción→HTTP contra Aiven) |
| 9 bis | CRUD de usuarios — **hueco del plan original**, ningún paso lo reclamaba | **Hecho y verificado (2026-10-01):** `user_service.py` migrado a las excepciones del paso 8 + chequeo de duplicado, `user_controller.py` con los 5 endpoints y las reglas de rol, alta en `router.py`. 15 comprobaciones: 401 en las 5 rutas sin token, los tres 403 con su `FORBIDDEN_ACTION`, 404/409, y el alta real contra Aiven (201 + fila en `authorities` + hash `$2a$10$`) con borrado físico de limpieza. **Pendiente de probar:** el camino feliz del borrado lógico |
| 10 | Ventas y cancelaciones: `venta_repository.py`, `venta_cancelada_repository.py`, `venta_service.py`, `venta_cancelada_service.py`, `venta_controller.py`, `venta_cancelada_controller.py` + dos altas en `router.py` | **Hecho y verificado (2026-10-05):** 49 comprobaciones de nivel 2. Los 7 endpoints dan 401 sin token; `/ventas/all` no se lo come `/{username}`; 204 en los dos GET de ventas y `200 []` en `/cancelaciones`; 200 (no 201) al registrar; 404 (no 500) al cancelar una venta inexistente; 422 sin `?responsable=`; el log guarda el username del token y no el `responsable`; el `id` del cliente se ignora en `POST /cancelaciones` |
| 11 | Activity log: `activity_log_controller.py` + alta en `router.py` con `require_role("SUPERADMIN")` | **Hecho y verificado (2026-10-04):** ruta en el OpenAPI con candado, 401 sin token, 403 con ADMIN y con SELLER, 200 con SUPERADMIN, `ipAddress` en camelCase, orden fecha/hora DESC, y `200 []` (no 204) con la lista vacía. Primer uso real de `require_role` |
| 12 | AEMPS + IA: `cima_service.py`, `ia_service.py`, `cima_controller.py` + alta en `router.py`, `lifespan` en `main.py` y `get_http_client` en `deps.py` | **Hecho y verificado (2026-10-11):** 30 comprobaciones de nivel 2 más 14 contra AEMPS de verdad. Las 3 rutas dan 401 sin token; 200 con el JSON de AEMPS sin doble serializar; 200 vacío con `nregistro` inexistente (AEMPS da 204); 502 con AEMPS caído, timeout, conexión rechazada y respuesta no-JSON; 409/404 con clave `mensaje`; **500 y no 502 en los cuatro fallos de la IA** (401, 5xx, timeout, caída) y sin escribir el log; `IA_MATCH` con el username del token; `tamanioPagina` no se reenvía; un `&` en el nombre no cuela parámetros; el cliente compartido se crea y se cierra con el `lifespan` |
| 13 | Tests: `pytest.ini` + `tests/` (13 ficheros) | **Hecho y verificado (2026-10-11):** **195 tests en verde en 1,6 s**, niveles 1 y 2, sin tocar Aiven. Y comprobado que la batería caza lo que dice cazar: cinco bugs reales inyectados de uno en uno (quitar el gate de `/articulos` de `router.py`, `require_role` con prefijo `ROLE_`, token de 24 h, el SELLER pudiendo crear usuarios, `/cancelaciones` devolviendo 204) la ponen roja los cinco. Detalle en §9 bis. **Nivel 3 empezado el 2026-10-13** (§9 ter): 3 tests × 2 versiones de MySQL con Testcontainers, fuera del `pytest` a secas |
| 14 | Docker y despliegue | **Hecho el 2026-10-12:** `Dockerfile`, `.dockerignore`, `docker-compose.yml` y workflow de build. Desplegado en **AWS** (ECR + OIDC + EC2 con rol de instancia, Fráncfort), probado contra Aiven desde allí. Queda automatizar el despliegue y meter los tests en el workflow. Detalle en §11 |

**Inventario de lo que falta, decisiones abiertas y trampas ya pagadas: §10.** Está escrito
para no repetir el análisis.

### Paso 9 — lo que se corrigió al revisarlo (2026-09-28)

Escrito por Jabier, revisado y corregido. Cinco cosas, dos de ellas bloqueantes:

1. **`from app.api.dependencies.auth_deps import get_current_username`** — `ModuleNotFoundError`:
   ese paquete no existe. Es `app/api/deps.py` (paso 7) y la función es `get_current_user`,
   que devuelve la entidad `Users`, no un `str`. **Tercera vez que aparece este patrón** (tras
   `from jose import` y `create_access_token(data=...)`): un import a un nombre plausible que
   nadie ha escrito. Sólo se caza ejecutando el fichero.
2. **`router.py` no incluía el router de artículos** — los siete endpoints no existían aunque
   el controlador estuviera completo. Es el equivalente a que Spring no escanee el
   `@RestController`.
3. **Cinco de los siete endpoints quedaban sin autenticar** (sólo `/insert` y `DELETE /{id}` la
   pedían). En el Java no hace falta declararlo ruta por ruta porque `SecurityConfig` acaba en
   `.anyRequest().authenticated()`. Se arregla con `dependencies=[Depends(get_current_user)]`
   en el `APIRouter`, que es el equivalente exacto; FastAPI cachea la dependencia por petición,
   así que los dos endpoints que además necesitan el usuario no provocan una segunda consulta.
4. **El paso 8 no se estaba usando**: el servicio lanzaba `ValueError` y el controlador lo
   traducía con tres `try/except`. Ahora lanza `ResourceNotFoundException` /
   `InsufficientStockException` y no queda ni un `try/except` en el controlador. De paso
   arregla que el mismo "no encontrado" saliera 400 en `/updateStock` y 404 en `/updateItem`.
5. **`ilike` → `like`** en `find_by_nombre_containing`: el comentario decía que `ilike` hacía
   falta para ignorar mayúsculas, pero en MySQL eso lo decide la *collation* de la columna
   (`utf8mb4_..._ci`), no el operador. `ilike` no existe en MySQL y SQLAlchemy lo compila a
   `LOWER(nombre) LIKE LOWER(%s)`, que impide usar el índice. Y `exists_by_id` devolvía el
   `1`/`0` de MySQL con la firma declarada `-> bool`.

**Trampa nueva al verificar, importante para el paso 13:** en FastAPI 0.141.1 **`app.routes` ya
no aplana los routers incluidos** — aparecen como un único objeto `_IncludedRouter`, así que
recorrer `app.routes` buscando las rutas de `/articulos` no encuentra nada y parece que no
están registradas. La fuente de verdad es `app.openapi()["paths"]`.

### Dos `get_db` gastaban el doble de conexiones (encontrado y corregido el 2026-09-28)

Salió al preguntar "¿no queda nada?" y revisar el proyecto entero en vez de fichero a fichero.

`api/deps.py` definía **su propio `get_db`**, copia del de `core/database.py` (paso 2). Casi
el mismo código —de hecho aquí había quedado la versión con el `try/finally` redundante que
allí ya se había corregido—, pero **FastAPI cachea las dependencias por identidad de la
función**: dos funciones distintas son dos dependencias distintas, así que una misma petición
abría **dos sesiones y dos conexiones**, una para el `session = Depends(get_db)` del endpoint
(que importaba el de `core.database`) y otra para la de `get_current_user`.

Medido con un listener `checkout` del pool: `GET /articulos/All` gastaba **2 de las 3**
conexiones (`pool_size=3, max_overflow=0`, fijado por la cuota de Aiven), así que cabía **una
sola petición autenticada simultánea** en vez de tres. Tras importar el `get_db` de
`core/database.py` en vez de redefinirlo: **1 conexión, 3 peticiones**.

Antes del arreglo del paso 9 esto afectaba sólo a `/insert` y `DELETE /{id}` (los dos únicos
que pedían token y además su propia sesión). Al añadir
`dependencies=[Depends(get_current_user)]` en el `APIRouter` para cerrar el agujero de
autenticación, pasó a afectar a **los siete**: arreglar una cosa amplió la otra. Los dos
arreglos son correctos, pero hay que mirarlos juntos.

**Regla para el resto de la migración:** una sola definición de cada dependencia, y `deps.py`
importa de `core/`, nunca reimplementa. Si un endpoint necesita sesión y usuario, las dos
dependencias tienen que resolverse al mismo objeto función.

**Pendiente de decisión (no es un descuido):** `DELETE /articulos/{id}` es un borrado físico y
**se lleva por delante el historial de ventas del artículo**. Comprobado en
`information_schema` de Aiven: `fk_articulos_ventas`, `ventas.codigo` → `articulos.codigo`,
`DELETE RULE: CASCADE`. Es el mismo caso que saltó con `users` en el paso 6, donde se pasó a
borrado lógico (`enabled=False`), pero `articulos` **no tiene columna `enabled`** y añadirla
es un cambio manual de esquema (`ddl-auto=none`) en la BD que comparte con el backend Java en
producción. El Java hace este mismo DELETE, así que por ahora se replica y queda avisado con
un comentario en el endpoint.

**Adelantado del paso 11:** `activity_log_repository.py` (`save` + `find_all_ordered`), porque el login necesita registrar `LOGIN_SUCCESS`/`LOGIN_FAILED` desde el principio.

**Bug encontrado y corregido en el paso 6, probando contra Aiven:** `authenticate_user`
no comprobaba `user.enabled` — un usuario deshabilitado seguía pudiendo entrar con la
contraseña correcta. Corregido comprobando `enabled` después de la contraseña. Ver
también la nota de `DELETE /users/{id}` en la §5, que depende del mismo campo.

**Tres bugs más encontrados y corregidos cerrando los pasos 6 y 7 (2026-09-27):**
- `activity_log_service.py` se escribió bien pero se guardó en `articulo_service.py`
  (la cabecera `# app/services/activity_log_service.py` no coincidía con la ruta real
  del fichero — la pestaña de PyCharm no era la que se creía). Movido a su sitio;
  `articulo_service.py` vuelve a quedar vacío, tal como estaba en el commit anterior
  (paso 9, aún pendiente).
- `auth_controller.py` llamaba a `create_access_token(data={"sub": ..., "rol": ...})`,
  la firma vieja (`dict` libre) que se eliminó a propósito en el paso 5 — reventaba con
  `TypeError` en cuanto se ejecutaba un login. Corregido a
  `create_access_token(username=..., role=...)`.
- `api/deps.py` importaba `from jose import JWTError, jwt` (librería no instalada vía
  `requirements.txt`; quedó suelta en el `.venv` de seguir el tutorial oficial de
  FastAPI) y `from app.core.config import settings` (no existe: solo hay
  `get_settings()`) con `settings.SECRET_KEY` (el campo real es `jwt_secret`). Corregido
  reutilizando `decode_access_token()` de `core/security.py`, que ya validaba el JWT
  desde el paso 5. No hizo falta tocar `requirements.txt`: la librería correcta
  (`PyJWT`) ya estaba declarada.

`app/main.py` ya registra el router (`app.include_router(api_router)`, antes comentado
como `TODO (paso 1)`) y `app/api/routes/router.py` ya no está vacío: agrupa
`auth_controller` con `APIRouter().include_router(...)`. La lista de orígenes CORS sale
de `Settings.cors_origins`, y `main.py` arranca uvicorn con el bucle de eventos correcto.

Verificar la configuración sin exponer la contraseña:

```bash
python -c "from app.core.config import get_settings; s=get_settings(); print(s.database_url.replace(s.db_password,'***'))"
```

---

### El gate de acceso, consolidado en `router.py` (2026-10-04)

Hasta ahora cada controlador llevaba su propio `dependencies=[Depends(get_current_user)]` en
el `APIRouter`. Funcionaba, pero **las reglas de acceso estaban repartidas por los ficheros**,
y eso es justo lo que permitió el mismo agujero dos pasos seguidos: 5 de 7 endpoints de
`/articulos` abiertos sin token (paso 9) y `GET /users/all` devolviendo 9 usuarios sin token
(paso 9 bis). Pregunta de Jabier que lo disparó: *"usas una cosa en uno y en otro no, ¿qué
lógica es esa?"* — tenía razón en el fondo, aunque el reparto no era aleatorio.

Ahora `router.py` es el **equivalente del `SecurityConfig.java`**: la tabla completa de qué
exige cada prefijo, leída de arriba abajo. Los controladores no dicen nada de autenticación.

| `SecurityConfig.java` | `router.py` |
|---|---|
| `.requestMatchers("/auth/**").permitAll()` | `include_router(auth_router)` — sin `dependencies` |
| `.anyRequest().authenticated()` | `dependencies=[Depends(get_current_user)]` |
| `.requestMatchers("/activity-log/**").hasRole("SUPERADMIN")` | `dependencies=[Depends(require_role("SUPERADMIN"))]` |

**La asimetría que hay que tener siempre presente**, y que explica los dos agujeros de arriba:

> En Spring, `.anyRequest().authenticated()` es un **cajón de sastre**: un `@RestController`
> nuevo nace protegido aunque te olvides de él.
> En FastAPI **no hay cajón de sastre**: un `include_router()` sin `dependencies` nace
> **ABIERTO**.

Por eso la lista de `router.py` es la checklist obligatoria al cerrar cada paso: si una línea
nueva no lleva `dependencies`, ese prefijo está público y nada avisa.

Tres detalles comprobados al hacer el traslado:

- **El candado de Swagger sobrevive.** Era el riesgo real de mover la dependencia al
  `include_router`: el `openapi()` sigue declarando `security` en las 14 operaciones
  protegidas, así que el botón *Authorize* de `/docs` funciona igual.
- **`require_role` ya depende de `get_current_user` por dentro**, así que la línea del
  activity log cubre también la autenticación: no hay que declarar las dos.
- **`hasRole("SUPERADMIN")` de Spring compara contra la authority `ROLE_SUPERADMIN`** (el
  prefijo lo añade Spring solo). `require_role` compara contra `Users.permiso` crudo de la BD,
  así que aquí se escribe **sin** prefijo. Con `"ROLE_SUPERADMIN"` no entraría nadie, y sin
  ruido: un 403 permanente. Es el mismo error del claim `role`/`rol` del paso 6 y del 9 bis.

Los controladores conservan su import de `get_current_user` **porque no es huérfano**: los
endpoints que necesitan saber *quién* llama lo siguen pidiendo como parámetro
(`articulo_controller.py` ×2, `user_controller.py` ×3), que es el equivalente del
`SecurityContextHolder`. Y no hay doble consulta a la BD: FastAPI cachea cada dependencia
dentro de la misma petición.

### Paso 11 — el detalle que no se podía copiar de `/articulos`

`GET /activity-log/all` **no lleva el `204 NO_CONTENT`** que sí tiene `GET /articulos/All`. No
es un descuido: los dos controladores del Java no hacen lo mismo, comprobado en el original
antes de escribirlo.

| Java | Comportamiento con lista vacía |
|---|---|
| `ArticuloController.java:44-50` | `if (articulos.isEmpty()) return noContent()` → **204** |
| `ActivityLogController.java:19` | devuelve la `List<ActivityLog>` pelada → **200 `[]`** |

Importa replicarlo porque un 204 no trae cuerpo, y un frontend que pintara la tabla del
historial se encontraría un `undefined` donde espera un array.

Tampoco hay `POST` ni `DELETE`, y es a propósito: el historial no se escribe nunca desde HTTP
—lo escribe el backend llamando a `ActivityLogService.log()`, por eso
`activity_log_schema.py` sólo tiene schema de salida— y sin endpoint de borrado el rastro de
auditoría no se puede limpiar.

### Paso 10 — lo que se encontró leyendo el Java (2026-10-05)

Seis cosas del original que cambian lo que hay que escribir, todas comprobadas antes de
escribir una línea:

1. **Registrar una venta NO descuenta stock.** `VentaService.java` inyecta
   `articulosRepository` y **no lo usa en ningún sitio**. Quien descuenta es el frontend, en
   una segunda petición: `carritocomponent.ts:157` llama a `actualizarStockBatch()` →
   `PUT /articulos/updateStock`. **Son dos peticiones sin transacción común:** si la segunda
   falla con 409, la venta ya está registrada y el stock sin tocar. Deuda real de producción;
   se replica tal cual, avisado con un comentario en el endpoint. Si algún día se arregla, el
   sitio es el service, descontando dentro de la misma transacción.
2. **Dos de los siete endpoints están muertos.** `POST /ventas/registrar` (singular) y
   `POST /cancelaciones` no los llama nadie en todo el Angular: el carrito usa sólo
   `/registrar/list` (`ventas-user.service.ts:47`), y `registrarCancelacion` existe en
   `ventas-canceladas.service.ts:31` sin que ningún componente la invoque. Se replican por
   contrato, pero **no hay frontend que los valide**.
3. **La colisión de rutas, otra vez.** `GET /ventas/all` y `GET /ventas/{username}` son el
   mismo método sobre el mismo prefijo, igual que en `/users`: `/all` va declarado **antes** o
   entra por `{username}` con `username="all"` y devuelve 204 sin que nadie se entere.
4. **El contraste de códigos dentro del mismo paso.** `/ventas` sí lleva 204 con lista vacía
   (`VentaController.java:34-36, 44-46`), `/cancelaciones` **no** (devuelve la `List` pelada,
   como el activity-log). Y `POST /ventas/registrar` da **200, no 201**, mientras
   `/users/insert` sí da 201. Es la lección del paso 11 repetida: el estilo de un endpoint no
   se copia del de al lado, se lee en su Java.
5. **`DELETE /ventas/cancelar/{id}` devuelve 200 con cuerpo vacío**, no 204
   (`ResponseEntity.ok().build()`, `VentaController.java:70`), al contrario que el DELETE de
   `/articulos`.
6. **El `responsable` viene por query param, no del token.** Un cliente puede firmar la
   cancelación con el nombre de otro, y el Java no lo valida. Por eso el `CANCEL_SALE` del
   activity log guarda **`current_user.username`**, el del token: `responsable` es quien firma
   en el historial, el log es quien lo pidió de verdad. Si alguien firma con otro nombre, ahí
   se ve.

Y una trampa de FastAPI que no existe en Spring: **las rutas de `/cancelaciones` son `""`, no
`"/"`.** El Java es `@GetMapping` sin path sobre `@RequestMapping("/cancelaciones")`, o sea
exactamente `/cancelaciones`. Con `@router.get("/")` la ruta sería `/cancelaciones/`, otra
distinta, y el frontend llama sin barra (`ventas-canceladas.service.ts:12`): se comería un
**307** en cada petición. Comprobado que tal como está, `/cancelaciones` responde 200 directo y
es `/cancelaciones/` la que redirige hacia ella.

#### Lo que se corrigió al revisar (ficheros 1, 3 y 4, escritos por Jabier)

1. **`VentaCanceladaRepository` acabó dentro de `venta_repository.py`**, con su propia cabecera
   `# app/repositories/venta_cancelada_repository.py` incluida, mientras el fichero de verdad
   seguía vacío. **Es el mismo fallo del paso 6** con `activity_log_service.py`: contenido
   correcto en la pestaña equivocada de PyCharm. Y el import **no lo caza**, porque el
   `from venta_repository import VentaRepository, VentaCanceladaRepository` del service
   apuntaba a donde sí estaba. Se vio con `dir()` del módulo que debía tenerlo.
2. **Y debajo iba lo caro: faltaba `find_all`.** `VentaCanceladaRepository` sólo tenía `save`,
   así que `GET /cancelaciones` no se podía hacer (`VentaCanceladaService.obtenerTodas()` es un
   `findAll()` pelado). Por esto no se para en el primer hallazgo.
3. **`cancelar_venta` lanzaba `ValueError`** con un comentario que decía *"más adelante el
   controlador atrapará esto"* — eso es volver al `try/except` que el paso 8 quitó. `ValueError`
   no tiene handler, cae en el genérico y da **500 donde toca 404**. Corregido a
   `ResourceNotFoundException`. (Era el aviso del §10: *todo lo escrito antes del paso 8 puede
   seguir con `ValueError`* — aquí era código nuevo, lo que lo hace más fácil de repetir.)
4. **`registrar_cancelacion` era el único "crear" del proyecto que recibía una entidad de
   SQLAlchemy** en vez de un schema. No es un agujero por sí mismo, pero con la entidad en la
   firma el controlador tiene que importar el modelo y montarla, y el único sitio donde se
   garantiza que no llegue un `id` del cliente pasa a ser ese controlador. Con
   `VentaCanceladaCreate` en la firma no hay nada que recordar: el schema no tiene campo `id`.
5. **Lo que estaba bien y se mantuvo:** quitar el `obtenerUsuarioAutenticado()` del service y
   pasar `username` como parámetro. El Java mete `SecurityContextHolder` dentro del `@Service`,
   lo que lo ata a Spring Security; así el service no sabe nada de autenticación ni de HTTP,
   igual que `core/security.py` no importa FastAPI.

#### Se quitó el `session.refresh()` de los cinco `save` (2026-10-05)

Había `refresh` en `articulo`, `user` y `activity_log`, y Jabier lo puso en `venta` pero no en
`venta_cancelada`. Preguntado qué unificar, decidió quitarlo. **Es un `SELECT` de más:**
`flush()` manda el INSERT y SQLAlchemy ya escribe de vuelta en el objeto la clave generada.
Comprobado ejecutando los cinco modelos:

```
Articulos id=1   Users id=1   ActivityLog id=1   Ventas id=1   VentaCancelada id=1
Articulos.version tras SOLO flush -> 1        (lo lleva SQLAlchemy por el version_id_col)
Users.enabled tras SOLO flush     -> True     (default de Python)
```

**Sigue haciendo falta cuando la columna la rellena el servidor** y Python no puede saberlo (un
`DEFAULT CURRENT_TIMESTAMP`, un trigger): ahí el objeto se quedaría con `None`. ~~En este
proyecto no hay ninguna.~~ **Corregido el 2026-10-13: sí hay una**, `ventas_canceladas.fecha`
es `datetime DEFAULT CURRENT_TIMESTAMP` en Aiven (visto en el `SHOW CREATE TABLE`, §9 ter). No
muerde porque `cancelar_venta` pasa siempre `fecha=datetime.now()` y el modelo tiene además
`default=datetime.now`, pero la afirmación era falsa: se hizo leyendo los modelos, no el
esquema. Y no hay riesgo de que los atributos se vacíen tras el `commit()`
porque `AsyncSessionLocal` va con `expire_on_commit=False` — con el defecto (`True`) un acceso
posterior intentaría recargar y en async eso revienta con `MissingGreenlet`.

Detalle relacionado, comprobado al tocar `VentaCancelada`: **SQLAlchemy aplica el `default` de
la columna incluso si le pasas `fecha=None` explícitamente**, no sólo cuando omites el campo.
Por eso el service puede pasar `fecha=datos.fecha` sin comprobar si viene vacío.

### El botón *Authorize* de Swagger: `HTTPBearer` en vez de `OAuth2PasswordBearer` (2026-10-11)

Salió al probar la imagen de Docker. `deps.py` declaraba
`OAuth2PasswordBearer(tokenUrl="/auth/login")`, que hace que `/docs` pinte el formulario del
flujo OAuth2 —usuario, contraseña, `client_id` y `client_secret`— **y no funcionaba**: ese
formulario envía las credenciales como `application/x-www-form-urlencoded` y `/auth/login`
espera JSON, porque es lo que manda el Angular. Medido contra el contenedor:

| Petición a `/auth/login` | Código |
|---|---|
| `username=ko2&password=1234&grant_type=password` (lo que manda el botón) | **422** |
| `{"username": "ko2", "password": "..."}` (lo que manda el Angular) | 401 / 200 |

El candado salía pintado en las 24 operaciones y no había forma de conseguir el token por ahí.
Además, `client_id` y `client_secret` identifican a la **aplicación** en un OAuth2 de verdad:
esta API no los usa ni los va a usar.

Se cambia a `HTTPBearer(auto_error=False)`, que pinta una sola caja donde se pega el token —
exactamente como el Swagger del backend Java. **No afecta al Angular**: el esquema de seguridad
vive sólo en el `openapi.json`, que únicamente lee Swagger.

Se descartó a propósito la alternativa cómoda (un `/auth/token` aparte que acepte formulario,
que es lo idiomático en FastAPI): sería una **segunda puerta de autenticación** que hay que
mantener en sintonía con la primera cada vez que cambie una regla del login, y un endpoint 26
que el Java no tiene. Decisión de Jabier tras ver las tres opciones.

`auto_error=False` y el 401 lanzado a mano, por dos motivos: así el cuerpo del error es el
mismo falte la cabecera o sea el token inválido, y el código que devuelve `HTTPBearer` por su
cuenta ha cambiado entre versiones de FastAPI (era 403, en la 0.141.1 es 401). Comprobado tras
el cambio, los tres casos iguales:

    sin cabecera          -> 401 {"detail": "No se pudieron validar las credenciales"}
    Bearer <token malo>   -> 401 (idem)
    Authorization sin "Bearer" -> 401 (idem)

y `WWW-Authenticate: Bearer` en los tres. Los 195 tests siguen en verde; el único que se cayó
fue el que comprueba el esquema del OpenAPI, que es justo para lo que estaba puesto.

---

## 8 bis. Los errores (paso 8) — lo que el Java hacía de verdad

Leyendo `GlobalExceptionHandler.java` y cruzándolo con el frontend Angular (2026-09-28):
**de sus cinco handlers sólo se disparaban dos.**

| Handler del Java | HTTP | ¿Se lanzaba? |
|---|---|---|
| `ExternalServiceException` | 502 | **Sí** — `CimaController`, en los tres `catch` del `RestTemplate` |
| `OptimisticLockException` | 409 | **Sí** — la lanza Hibernate solo, por el `@Version` de `Articulos` |
| `Exception` (genérico) | 500 | **Sí**, y de más: se come todos los `RuntimeException` de abajo |
| `ResourceNotFoundException` | 404 | **No.** Clase declarada, handler escrito, `throw` en ningún sitio |
| `IllegalArgumentException` | 400 | **No.** Nada del proyecto la lanza |

Los "no encontrado" de verdad (`ArticuloService` líneas 39, 52, 96, 104; `UserService` 46)
lanzan `RuntimeException` pelado → caen en el genérico → **el cliente recibe un 500**, no
un 404.

Y los 409/404 que el frontend sí mira **no pasan por el handler**: son
`ResponseEntity.status(...)` escritos a mano en el controlador
(`CimaController.validarMedicamento` para "producto ya existe" y "sin resultados en AEMPS",
`UserController.insertarUsuario` para "el usuario ya existe").

**El frontend nunca lee el cuerpo del error, sólo `err.status`.** En todo `src/app` hay
exactamente cuatro comprobaciones de código: 401/403 en `auth.interceptor.ts` (borra el token
y va a login), y tres 409 con mensaje propio hardcodeado en Angular
(`almacen.component.ts:307` + su 404 de AEMPS en la línea 309, `carritocomponent.ts:189`
para el conflicto de stock, `users.component.ts:199` para el usuario duplicado). El resto de
errores cae en un `else` genérico. **Consecuencia: la forma del JSON de error es libre**
(el Java mezclaba `{"error":...}`, `{"mensaje":...}` y strings sueltos), y devolver 404 donde
el Java daba 500 no rompe nada.

Por eso en Python hay **cuatro** excepciones y no dos:

| `exceptions/custom.py` | HTTP | Para qué |
|---|---|---|
| `ResourceNotFoundException` | 404 | Artículo/usuario/venta que no existe. **Desviación deliberada**: en el Java esto era un 500 |
| `DuplicateResourceException` | 409 | Unifica los dos chequeos de duplicado que el Java tenía sueltos en cada controlador |
| `InsufficientStockException` | 409 | No hay unidades para vender. En el Java iba en el MISMO `throw` que el "no encontrado" (`ArticuloService.java:39`) y salía 500 |
| `ExternalServiceException` | 502 | **AEMPS** caído. Único nombre copiado tal cual del Java |

**Hubo una quinta, `AempsNotFoundException`, y se borró en el paso 12.** La escribió el paso 8
para el 404 de "AEMPS sin resultados", pero al llegar al paso 12 resultó que ese 404 del Java
lleva la clave `mensaje` y el handler emitía `error`, así que el controlador lo devuelve a mano
y la clase se quedó sin un solo `raise`. Era exactamente el defecto que este mismo documento le
señala al Java (clase declarada, handler registrado, nadie la lanza), así que fuera.

**Ojo con el 502: es sólo de AEMPS, no del microservicio de IA.** Un fallo de la IA da **500**
porque el Java no lo captura. Está explicado en el §5.

Más, en `handlers.py` y sin clase propia: `StaleDataError` de SQLAlchemy → **409**, que es el
equivalente async del `OptimisticLockException` de Hibernate (la lanza el flush/commit cuando
el `version_id_col` de la fila ya no es el que se leyó), y `Exception` → 500 con el traceback
al log y nunca al cliente.

No se replica el handler de `IllegalArgumentException` (400): en el Java no lo lanza nadie, y
aquí la validación de entrada ya la hace Pydantic con un 422.

**Registro a mano.** FastAPI no tiene `@RestControllerAdvice`: los handlers se enganchan con
`app.add_exception_handler(...)`, agrupados en `register_exception_handlers(app)` y llamados
desde `main.py`. Comprobado que el handler de `Exception` **no** tapa las respuestas normales
de FastAPI: `/auth/protected` sin token sigue dando su 401 `{"detail":"Not authenticated"}`,
porque Starlette busca el handler recorriendo el MRO y `HTTPException` tiene el suyo propio.

**Trampa al verificarlo**: `TestClient(app)` re-lanza la excepción no controlada en vez de
dejar que el handler genérico la convierta en 500. Hace falta
`TestClient(app, raise_server_exceptions=False)` para ver el 500 de verdad.

---

## 9. Los tests (paso 13) — decisión cerrada el 2026-09-28

**No se usa SQLite como "el H2 de los tests".** Esta frase estaba en este documento y en la
memoria desde el paso 3; queda anulada por lo de abajo. Sigue valiendo para una comprobación
suelta de un `INSERT` a mano mientras se escribe una capa, pero **no** como base de datos de
la batería de tests.

Motivo, con dos pruebas de la propia migración: los dos peores bugs encontrados hasta ahora
son cascadas de borrado (`fk_usuario_ventas` en el paso 6, `fk_articulos_ventas` en el 9), y
**los dos pasan en verde sobre SQLite**, por dos razones que se suman:

1. **SQLite ignora las claves ajenas** salvo `PRAGMA foreign_keys=ON` en *cada* conexión.
2. Y aunque se active: **los modelos Python no declaran esas FK** (ver `venta_model.py`:
   `codigo` es un `String(13)` pelado, sin `ForeignKey`). Un `Base.metadata.create_all()`
   construye por tanto un esquema **sin** esas cascadas.

Es consecuencia directa de `ddl-auto=none`: el esquema real de Aiven se hizo a mano y tiene
constraints que los modelos no conocen. Cualquier test que se cree su propio esquema prueba
una base de datos que no existe. (De propina: el `LIKE` de SQLite sólo ignora mayúsculas en
ASCII, así que divergiría de la collation `utf8mb4_..._ci` en nombres con acentos o `ñ`.)

### Los tres niveles

| Nivel | Equivalente Java | Qué prueba | BD |
|---|---|---|---|
| 1. Unitario con mocks | JUnit + Mockito | `core/security.py` (claims, caducidad, `alg=none`), `_generar_codigo_unico`, reglas de los servicios | Ninguna |
| 2. Contrato HTTP | `@WebMvcTest` + `@MockBean` | los 401/403/404/409, las claves camelCase, que cada ruta exija token | Ninguna |
| 3. Integración | `@SpringBootTest` + **Testcontainers** | las cascadas, la collation, el bloqueo optimista, las transacciones | MySQL real |

**Los niveles 1 y 2 desde el primer día; el 3 sólo para la media docena de casos donde MySQL
importa de verdad.** Se llegará al nivel 3 si da tiempo — no es requisito para cerrar el paso 13.
**Empezado el 2026-10-13: ver §9 ter.**

El nivel 2 ya se está usando de hecho en los scripts de verificación de los pasos 8 y 9:
`app.dependency_overrides[get_current_user] = ...` es literalmente el `@MockBean` de Spring, y
`httpx.AsyncClient(ASGITransport(app=app))` el `MockMvc`. Cubre todo el contrato con el
frontend Angular (que sólo mira el `status`, ver §8 bis) sin tocar Aiven.

Para el nivel 3, el equivalente honesto de H2 es **Testcontainers** (`testcontainers[mysql]`):
levanta un MySQL en Docker, se le carga el esquema real y ahí sí aparecen las cascadas. La
alternativa sin Docker es una segunda base de datos en el mismo Aiven, pero entonces los tests
dependen de la red.

### Vocabulario

| Java | Python |
|---|---|
| JUnit | `pytest` |
| `@Mock` / `when().thenReturn()` | `unittest.mock.AsyncMock` |
| `@MockBean` | `app.dependency_overrides[dep] = ...` |
| `MockMvc` | `httpx.AsyncClient(ASGITransport(app))` |
| `@BeforeEach` | `@pytest.fixture` |
| `@Test` sobre método async | `@pytest.mark.asyncio` |

`pytest` y `pytest-asyncio` ya están en `requirements-dev.txt` desde el paso 1 (fuera de la
imagen Docker), y `tests/conftest.py` existe vacío esperando las fixtures.

**Trampa ya conocida para cuando se escriban:** en FastAPI 0.141.1 `app.routes` no aplana los
routers incluidos, así que para comprobar qué rutas hay registradas se usa
`app.openapi()["paths"]`. Y `TestClient` re-lanza la excepción no controlada en vez de dejar
que el handler dé el 500: hace falta `raise_server_exceptions=False`.

**El `conftest.py` tiene que cerrar el engine en el *teardown*.** Visto el 2026-10-01 al
verificar el paso 9 bis: un script que acaba sin `await engine.dispose()` suelta
`RuntimeError: Event loop is closed` desde el `__del__` de la conexión de `aiomysql` — el
recolector intenta cerrar el socket TLS cuando `asyncio.run()` ya ha cerrado el bucle. No
afecta al resultado (sale *después* de que todo haya terminado bien), pero en una batería de
tests lo escupe cada fichero y entierra la salida de verdad. La fixture del engine va con
`yield` y `await engine.dispose()` detrás — el equivalente del `@PreDestroy` que Spring
ejecutaba solo sobre el `DataSource`.

---

## 9 bis. Los tests escritos (paso 13, cerrado el 2026-10-11)

**195 tests, 13 ficheros, 1,6 s, ni una conexión a Aiven.** Niveles 1 y 2 del §9. El nivel 3
(Testcontainers) se empezó el 2026-10-13 y va aparte: §9 ter.

| Fichero | Tests | Qué fija |
|---|---|---|
| `conftest.py` | — | las fixtures: cliente, sesión falsa, `autenticar`, cliente HTTP falso, fábricas de entidades |
| `test_security.py` | 17 | nivel 1: los 4 claims del JWT, las 10 h, el rol sin `ROLE_`, los 6 rechazos (manipulado, otro secreto, caducado, `alg=none`, sin `sub`, sin `exp`) y bcrypt `$2a$10$` |
| `test_router_gate.py` | 26 | el inventario de las 26 operaciones y que sólo `/` y `/auth/login` están abiertas, leído del OpenAPI **y** comprobado con 24 peticiones sin token |
| `test_health.py` | 4 | `/`, el OpenAPI y el `tokenUrl` del botón *Authorize* |
| `test_auth_controller.py` | 14 | login 200/401/422, el token emitido, `LOGIN_SUCCESS` y `LOGIN_FAILED` |
| `test_articulo_controller.py` | 22 | los 204, el 404 del lote vacío, 404/409/409 de las excepciones, `aempsCode` |
| `test_user_controller.py` | 25 | las tres reglas de rol con su control negativo, 201, 409, 404 |
| `test_venta_controller.py` | 15 | 204 vs 200, el 200 que no es 201, el 422 sin `responsable`, quién firma vs quién lo pide |
| `test_venta_cancelada_controller.py` | 7 | el `200 []` que **no** es 204, el no-307, el `id` del cliente ignorado |
| `test_activity_log_controller.py` | 9 | 401/403/403/200 y el `200 []` |
| `test_cima_controller.py` | 22 | el JSON sin doble serializar, el 204 de AEMPS, los 502, y **el 500 de la IA sin `IA_MATCH`** |
| `test_articulo_service.py` | 12 | nivel 1: el lote que se corta entero, el límite exacto del stock, el bucle del código único |
| `test_user_service.py` | 15 | nivel 1: los tres `None` de `authenticate_user`, el duplicado antes de hashear, el borrado lógico |
| `test_venta_service.py` | 7 | nivel 1: la transacción de dos escrituras de `cancelar_venta` |

**La batería está probada contra sí misma.** Se inyectaron cinco bugs reales, de uno en uno, y
los cinco la ponen roja (los ficheros se restauraron después):

| Bug inyectado | Resultado |
|---|---|
| `include_router(articulo_router)` sin `dependencies` | 6 fallos |
| `require_role` comparando con el prefijo `ROLE_` | 5 fallos |
| `ACCESS_TOKEN_EXPIRE_HOURS = 24` | 1 fallo |
| El SELLER vuelve a poder crear usuarios (como en el Java) | 1 fallo |
| `/cancelaciones` devolviendo 204 con lista vacía | 1 fallo |

Lo que se aprendió escribiéndolos, y no estaba en el §9:

- **`ASGITransport` necesita `raise_app_exceptions=False`.** Es el equivalente del
  `raise_server_exceptions=False` del `TestClient`: Starlette, *después* de pasar la excepción
  por el handler genérico, siempre la vuelve a lanzar. Medido: con el valor por defecto el test
  recibe el `RuntimeError` pelado; con `False`, el `500 {"error": ...}`. Sin esto no se puede
  probar el 500 de la IA.
- **Los hijos de un `AsyncMock` también son `AsyncMock`.** Fingir
  `session.execute(...).scalar_one_or_none()` con el mock por defecto devuelve una **corrutina**,
  y el service revienta con `AttributeError: 'coroutine' object has no attribute 'role'`, que no
  se parece en nada al problema. Hay que montar ese trozo con `MagicMock` a mano.
- **`spec=AsyncSession` en la sesión falsa** convierte un `sesion.commti()` en `AttributeError`
  en vez de en un mock nuevo que pasa en verde. Es la red contra el bug recurrente del proyecto.
- **El mock del repositorio tiene que cubrir el método que el service usa de verdad.**
  `delete_articulo_by_id` comprueba con `exists_by_id`, no con `find_by_id`; al dejarla sin
  mockear, el repositorio real corrió contra la sesión falsa y `result.scalar()` devolvió un
  mock "verdadero". Lo cazó el test, no el import.
- **El `.env` se resolvía contra el directorio de trabajo** (`env_file=".env"`), así que lanzar
  los tests desde otra carpeta mataba el import de la app con los 9 campos obligatorios de
  `Settings` ausentes — y era el mismo motivo por el que PyCharm no podía ejecutar
  `app\main.py`. Arreglado con `_PROJECT_ROOT / ".env"`, el mismo criterio que ya tenía el
  `ca.pem`.
- **No hace falta cerrar el engine** en los niveles 1 y 2: no se abre ninguna conexión (medido,
  `engine.pool.checkedout() == 0`). El `await engine.dispose()` del §9 hará falta cuando llegue
  el nivel 3.

---

## 9 ter. El nivel 3: Testcontainers contra el esquema real (empezado el 2026-10-13)

```bash
pytest -m integration     # Docker arrancado; ~30 s: 3 tests x 2 versiones de MySQL
pytest                    # los 195 de siempre; el nivel 3 sale como "6 deselected"
```

| Fichero | Qué es |
|---|---|
| `tests/schema.sql` | El esquema **real** de Aiven, sacado con `SHOW CREATE TABLE` el 13/10. Sólo DDL |
| `tests/integration/conftest.py` | Contenedor por versión, carga del esquema, vaciado entre tests, sesión real |
| `tests/integration/test_venta_cancelada_mysql.py` | Los 3 primeros tests (abajo) |
| `pytest.ini` | marcador `integration` y `addopts = -m "not integration"` |
| `requirements-dev.txt` | `testcontainers[mysql]==4.15.0` |

### Por qué un `schema.sql` y no `Base.metadata.create_all()`

Lo que ya decía el §9, ahora medido: los modelos no declaran ni una `ForeignKey`, así que un
`create_all()` construye una base **sin** las tres cascadas. Con el esquema real cargado en un
contenedor, comprobado en las dos versiones: borrar un artículo se lleva sus ventas, borrar un
usuario se lleva sus ventas y su fila de `authorities`.

**Si cambia el esquema de Aiven, hay que volver a volcarlo.** El fichero es una foto: nadie lo
mantiene sincronizado solo.

### Las dos versiones de MySQL

Aiven corre **8.0.45** y pasa a **8.4** después del 31/10/2026, sin poder evitarlo. La
batería entera corre en las dos (`params=` en la fixture `mysql`), así que esa subida queda
probada antes de que ocurra — la prueba que el 10/10 no se pudo hacer porque el plan gratuito
de Aiven no permite *fork*. Resultado a 13/10: **mismo comportamiento en las dos**, y el cambio
de 8.4 que podía romper algo (claves ajenas a columnas no únicas) no aplica: las tres apuntan a
`UNIQUE`.

**Después del 31/10:** quitar `mysql:8.0.45` de `_IMAGENES` y cambiar `mysql:8.4` por la
versión exacta que dé `SELECT VERSION()` en Aiven. `mysql:8.4` a secas es el último parche
(8.4.11 el 13/10), no necesariamente el de producción.

### Lo que el volcado enseñó: el modelo y la base no coinciden

| Columna | En Aiven | En el modelo | Efecto |
|---|---|---|---|
| `ventas_canceladas.nombre_producto` | `varchar(255)` **NOT NULL** | `String(100)`, `Optional` | cancelar una venta con `nameproducto` NULL → `ERROR 1048` → **500** |
| `ventas_canceladas.importe` | **`decimal(10,2)`** NOT NULL | `Double`, `Optional` | 25.905 se guarda como 25.91 |
| `ventas_canceladas.fecha` | `DEFAULT CURRENT_TIMESTAMP` | sin default de servidor | el §7 decía que no había ninguna (corregido) |
| `users.permiso` | `varchar(20)` DEFAULT `'SELLER'` | `String(50)` | un permiso de más de 20 caracteres no cabe |
| `ventas.nameproducto`, `ventas.dnicliente` | admiten **NULL** | `Mapped[str]`; `VentaOut` los exige | una sola fila con NULL tumbaría `GET /ventas/all` entero con un 500 |

**Comprobado en Aiven el 13/10:** `SELECT COUNT(*) FROM ventas WHERE nameproducto IS NULL OR
dnicliente IS NULL` → **0**. Las dos últimas filas son un riesgo latente, no un fallo activo. Por
la API de Python no puede entrar un NULL (`VentaCreate` exige los dos campos); por el Java, sin
comprobar. Ninguna se ha arreglado: está en la bitácora.

Menores, sin efecto: `authorities.id`, `ventas_canceladas.id` y `activity_log.id` son `bigint`
(el modelo dice `Integer`) y `articulos.codigo` es `char(13)` (el modelo, `String(13)`).

**Collation:** cuatro tablas en `utf8mb4_general_ci` y **dos en `utf8mb4_0900_ai_ci`**
(`activity_log` y `ventas_canceladas`), leído de `information_schema.TABLES`. Las dos ignoran
mayúsculas **y acentos**: medido, `LIKE '%nino%'` encuentra `Niño`.

### Los tres tests

Son de **caracterización**: fijan lo que la aplicación hace hoy, no lo que debería hacer.

| Test | Qué fija |
|---|---|
| `test_cancelar_venta_sin_nombre_revienta_con_error_1048` | la causa: `IntegrityError` con código 1048 en `nombre_producto` |
| `test_endpoint_cancelar_venta_sin_nombre_hoy_da_500_y_no_borra` | la consecuencia: 500, la venta sigue y no queda cancelación huérfana |
| `test_endpoint_cancelar_venta_con_nombre_da_200` | el control: sin él, el 500 podría venir de cualquier otra cosa |

**Probados contra sí mismos:** quitando el `NOT NULL` de `schema.sql`, los dos primeros se
ponen rojos en las dos versiones (4 fallos) y el control sigue verde. El día que se decida qué
hacer con una venta sin nombre, esos dos se pondrán rojos a propósito.

### Trampas, todas pagadas el 13/10

- **`ANSI_QUOTES`.** Aiven lo lleva en el `sql_mode`, y por eso su `SHOW CREATE TABLE` sale con
  `"users"`. En un MySQL normal eso se lee como **cadena**: `ERROR 1064`. El `schema.sql` va con
  backticks.
- **El bucle de eventos.** `pytest-asyncio` en Windows crea un `ProactorEventLoop` (medido).
  Se fuerza el Selector con el hook `pytest_asyncio_loop_factories`, **no** sobrescribiendo
  `event_loop_policy`: eso está *deprecated* en pytest-asyncio 1.4 y
  `WindowsSelectorEventLoopPolicy` desaparece en Python 3.16.
- **`dialect="aiomysql"` rompe el arranque del contenedor.** Testcontainers usa esa URL con un
  `create_engine()` **síncrono** para ver si MySQL está listo → `MissingGreenlet`. La URL async
  se monta a mano.
- **`seed=` va en carrera.** Testcontainers copia esos ficheros *después* de arrancar el
  contenedor, compitiendo con el entrypoint de MySQL. El esquema se carga a mano con PyMySQL,
  una vez listo.
- **Ryuk falla en Docker Desktop** (`Port mapping ... port 8080 is not available`:
  `DockerClient.port()` no reintenta, y el reintento de fuera choca con un 409). Apagado **sólo
  en Windows**. Si se mata pytest a lo bruto, el MySQL se queda vivo:
  `docker ps --filter "ancestor=mysql:8.4"`.
- **Sin TLS, PyMySQL necesita `cryptography`** para el `caching_sha2_password` (cifra la
  contraseña con RSA). Lo trae el extra `[mysql]`; en producción no hace falta porque Aiven va
  por TLS.
- **El cliente `mysql` del contenedor habla `latin1` por defecto.** Una prueba a mano con `ñ`
  dio un falso "no encuentra": la `ñ` se había guardado rota. Con `--default-character-set=utf8mb4`,
  bien. Antes de sacar conclusiones de la collation, mirar el `HEX()` de lo guardado.
- **MySQL arranca dos veces** (un servidor temporal sin red para inicializar, y luego el de
  verdad). Contar líneas `ready for connections` en los logs no sirve, porque también cuenta las
  del X Plugin. Lo fiable es una conexión TCP. Testcontainers entra por TCP y no le afecta.

### Diseño de las fixtures, y por qué

- **Contenedor de ámbito de sesión** y fixture **síncrona**: arranca una vez por versión
  (~12 s) y no choca con `asyncio_default_fixture_loop_scope = function`.
- **Engine por test**, con `NullPool` y `dispose()` al final: un engine async queda atado al
  bucle en el que abre conexiones, y cada test tiene el suyo.
- **`TRUNCATE` antes de cada test** en vez de transacción con rollback: los services hacen
  `commit()` de verdad, y el bloqueo optimista necesitará dos sesiones con datos confirmados.
- **`sesion` se sobrescribe por nombre**: la de `tests/integration/conftest.py` tapa a la falsa
  de `tests/conftest.py` sólo en esa carpeta (comprobado). La petición HTTP abre **su propia**
  sesión, como el `get_db` real; si usara la del test, el test vería objetos en memoria y no lo
  que quedó en MySQL.
- **El marcador lo pone el `conftest`** (`pytest_collection_modifyitems` con `tryfirst=True`),
  no cada fichero, para que un test nuevo no se cuele en el `pytest` a secas y tumbe la CI.

### Lo que falta del nivel 3

1. La cascada de `DELETE /articulos/{id}` por el endpoint (comprobada a mano en SQL, falta el test).
2. El bloqueo optimista: dos sesiones sobre el mismo artículo, la segunda → `StaleDataError` → 409.
3. La collation desde `find_by_nombre_containing`.
4. Un job `integration` en `deploy.yml` (en `ubuntu-latest` hay Docker y Ryuk funciona).
5. Decidir qué hacer con una venta sin `nameproducto` al cancelar: va con el rediseño de la
   cancelación (reponer stock), en la bitácora.

---

## 10. Pendientes — inventario y análisis ya hecho

*Cerrado el 2026-09-28. **Esto está escrito para no repetir el mismo análisis tres veces**: si
algo de aquí se contradice con el código, gana el código, pero el razonamiento no hay que
volver a hacerlo.*

**Estado en una línea:** *(2026-10-11)* **los 25 endpoints vivos** (`/auth` ×2 +
`/articulos` ×7 + `/users` ×5 + `/ventas` ×5 + `/cancelaciones` ×2 + `/activity-log` ×1 +
`/api/cima` ×3). **No queda código de negocio pendiente, y desde el 2026-10-11 tampoco tests**: 195 en verde
(§9 bis). **El paso 14 se cerró el 2026-10-12**: tras el ejercicio de AWS (§11, ya desmontado) la API corre en Hetzner con la imagen de `ghcr.io`, y el workflow ejecuta los 195 tests antes de publicarla. *(2026-10-13)* Nivel 3 empezado: 3 tests contra MySQL real en 8.0.45 y 8.4 (§9 ter). Lo que queda: más tests de nivel 3 y su job en la CI, automatizar el despliegue y el microservicio de IA.

| Paso | Qué falta | Ficheros vacíos |
|---|---|---|
| ~~9 bis~~ | ~~CRUD de usuarios~~ — **hecho el 2026-10-01** | — |
| ~~10~~ | ~~Ventas y cancelaciones~~ — **hecho el 2026-10-05** | — |
| ~~11~~ | ~~Activity log: sólo falta exponerlo~~ — **hecho el 2026-10-04** | — |
| ~~12~~ | ~~AEMPS + microservicio IA~~ — **hecho el 2026-10-11** | — |
| ~~13~~ | ~~Tests~~ — **hecho el 2026-10-11**, 195 en verde (§9 bis) | — |
| 14 | Docker y despliegue | `Dockerfile`, `docker-compose.yml`, workflow |

### Dos cosas que salieron del paso 12 y afectan a otros pasos

**1. La IP del `activity_log` será la del proxy, no la del cliente — se arregla en el paso 14.**
El Java tiene `server.forward-headers-strategy=framework` (`application.properties:32`), que
hace que `getRemoteAddr()` devuelva la IP real del navegador leyendo `X-Forwarded-For`. En
Python, `request.client.host` es el otro extremo del socket: detrás de nginx o de Docker
guardará la IP del proxy. **Afecta a los logs de los pasos 9 bis, 10, 11 y 12**, no sólo al
`IA_MATCH`. Es configuración de uvicorn, no código: hace falta `--forwarded-allow-ips` en el
`CMD` del Dockerfile (medido: con el valor por defecto `127.0.0.1`, un proxy que hable desde
`172.18.0.1` no se considera de confianza y la cabecera se ignora).

**2. `get_current_user` ahora hace `commit()` para soltar la conexión del pool.** Lo descubrió
el paso 12 porque es el primero que habla con servicios externos: el `SELECT` de autenticación
retenía una de las 3 conexiones de Aiven **hasta el final de la petición**, así que tres
búsquedas lentas simultáneas (AEMPS hasta 10 s, IA hasta 30) dejaban sin BD al resto de la API.
Medido: `checkedout=1` antes del `commit()`, `0` después.

**No usar `rollback()` para esto**, aunque también suelte la conexión: caduca los atributos de
la entidad (`expired_attributes = ['id', 'name']` tras `rollback`, `[]` tras `commit`, aun con
`expire_on_commit=False`), y el primer `current_user.username` del endpoint intentaría recargar
la fila — en async, `MissingGreenlet`.

Del **paso 10** no hay que volver a analizar nada: lo que el Java hace de verdad (que registrar
una venta no descuenta stock, los dos endpoints muertos, el contraste de 204 entre `/ventas` y
`/cancelaciones`) está en el §8. ~~**El paso 12 es el único que queda de código de negocio**, y
es el más complejo de los 25 por el flujo de `/api/cima/validar` (§5).~~ **Cerrado el
2026-10-11; ya no queda código de negocio pendiente.** Lo que se descubrió al escribirlo —el
500 de la IA, el 204 de AEMPS, el `tamanioPagina` que nadie usa— está en el §5.

~~Del paso 11 ya están hechos `activity_log_repository.py` y `activity_log_service.py`
(adelantados en el paso 6 porque el login los necesitaba): falta **sólo el controlador**.~~
**Cerrado el 2026-10-04** y aquí sí era sólo el controlador. Era el **único de los 25
endpoints que no es "autenticado" a secas** y estrenó el `require_role("SUPERADMIN")` que
estaba en `deps.py` sin usar desde el paso 7. Lo que no era obvio (el `204` que *no* hay que
copiar de `/articulos`) está en el §8.

### El hueco: `/users` no lo reclama ninguno de los 14 pasos

El paso 6 escribió `user_repository.py` y `user_service.py`, pero **sólo para el login**. Los
cinco endpoints `/users/**` no tienen dueño en la tabla del §7, y ahí viven las reglas de
autorización que se aparcaron a propósito en el paso 7. Queda como **paso 9 bis**.

**Y no era sólo el controlador** (esta sección lo daba por hecho; corregido el 2026-10-01 al
empezar el paso): `user_service.py` se escribió en el paso 6, *antes* de que existieran las
excepciones del paso 8, así que seguía lanzando `ValueError` en `actualizar_usuario` y en
`delete_user_by_id` — y `ValueError` no tiene handler, caía en el genérico y habría dado **500
donde toca 404**. Además `crear_usuario` no comprobaba el duplicado, de modo que un `username`
repetido llegaba al `INSERT` y moría con el error de clave única de MySQL, otro 500 donde el
Java devuelve 409. Las dos cosas arregladas y probadas contra Aiven; el chequeo del duplicado
va **antes** de hashear, que bcrypt cuesta ~50 ms.

Lo que hay que replicar de `UserController.java`, ya leído y analizado:

| Endpoint | Comportamiento del Java |
|---|---|
| `GET /users/all` | lista; si está vacía → **204** |
| `GET /users/{username}` | no encontrado → **404** |
| `POST /users/insert` | duplicado → **409**; éxito → **201 CREATED**; log `INSERT_USER` |
| `PUT /users/update` | objetivo inexistente → **404** |
| `DELETE /users/{id}` | objetivo inexistente → **404**; éxito → **204**; log `DELETE_USER`. **Borrado lógico**, ver la nota del §5 |

**Las tres reglas finas, y por qué no son un `require_role`:** dependen del rol del usuario
**objetivo**, no del que llama, así que no se pueden expresar como una dependencia de ruta.
Son lógica de servicio/controlador:

1. `POST /users/insert` — un `ADMIN` sólo puede crear `SELLER`.
2. `PUT /users/update` — un `ADMIN` no puede modificar a un `ADMIN` ni a un `SUPERADMIN`.
3. `DELETE /users/{id}` — un `ADMIN` no puede borrar a un `ADMIN` ni a un `SUPERADMIN`.

Las tres devuelven **403** y, antes de devolverlo, **registran un `FORBIDDEN_ACTION`** en el
activity log con el detalle del intento y la IP. Eso hay que replicarlo: es rastro de
seguridad, no un adorno.

El `obtenerRolDelCaller()` del Java saca el rol del primer *authority* del
`SecurityContextHolder` y le quita el prefijo `ROLE_`. **En Python no hace falta nada de eso**:
`get_current_user` ya devuelve la entidad y `current_user.permiso` trae el valor crudo
(`"ADMIN"`, no `"ROLE_ADMIN"`) — ver §6 bis.

**Trampa de orden de rutas, en FastAPI sí importa:** `GET /users/all` y
`GET /users/{username}` son el mismo método sobre el mismo prefijo. FastAPI resuelve **por
orden de declaración**, así que si `/{username}` se declara primero, se come `all` como si
fuera un nombre de usuario y `/users/all` nunca se ejecuta. Spring elegía la ruta literal por
ser más específica y esto no pasaba. **`/users/all` va declarado antes.** (En `/articulos` no
llegó a pasar: `/All` y `/{id}` no colisionan porque son métodos distintos.)

**Cerrado el 2026-10-01.** Lo escribió Jabier y lo revisé yo. Los cuatro fallos que tenía, por
si vuelven a aparecer en los pasos 10-12, que son el mismo patrón:

1. **El import inventado otra vez** (cuarta vez en el proyecto, y la misma ruta que en el paso
   9): `app.api.dependencies.auth_deps.get_current_token_payload`. No existe el paquete ni la
   función.
2. **Y debajo, el fallo de verdad:** leía el rol con `token_payload.get("rol", "")` cuando el
   claim se llama **`role`** (§6 bis). Eso devuelve `""` para todo el mundo, así que las tres
   reglas finas **no se disparaban nunca**: ni el 403 ni el `FORBIDDEN_ACTION`. Un endpoint roto
   se nota; una regla de seguridad que nunca salta, no. Arreglado usando `get_current_user` y
   `current_user.permiso`, que además es más estricto que el Java: el `SecurityContextHolder`
   saca el rol del token, así que a quien le bajen el rol sigue siendo ADMIN hasta que caduque.
3. **`router.py` incluía el módulo, no el router** (`include_router(user_controller)`):
   `AttributeError: module ... has no attribute '_contains_router'` al arrancar.
4. **Faltaba `dependencies=[Depends(get_current_user)]` en el `APIRouter`** — el mismo agujero
   del paso 9. Medido sin cabecera `Authorization`: `GET /users/all` → **200 con los 9 usuarios**
   y `GET /users/{username}` → 200; los otros tres ya pedían token porque reciben al llamante
   como parámetro.

Y una limpieza: el chequeo de duplicado estaba **dos veces** (en el controlador, fiel al Java, y
en `UserService.crear_usuario` desde ese mismo día). Se quedó el del service, que es el que no
se puede saltar; eran dos `SELECT` por alta para la misma pregunta.

**Lo que falta de 9 bis:** probar el camino feliz del borrado lógico (que `DELETE` deja
`enabled=False` y las ventas intactas). Se aparcó a propósito el 2026-10-01: para probarlo hay
que crear un usuario, darle una venta y dejar la fila deshabilitada en Aiven.

### Decisiones abiertas — ninguna es un descuido

1. **`DELETE /articulos/{id}` borra el historial de ventas.** `fk_articulos_ventas`
   (`ventas.codigo` → `articulos.codigo`) es `ON DELETE CASCADE`. Mismo caso que `users` en el
   paso 6, pero `articulos` no tiene columna `enabled` y añadirla es un cambio manual de
   esquema (`ddl-auto=none`) en la BD que comparte con el Java en producción. **Decidido el
   2026-09-28: se deja como el Java**, avisado con un comentario en el endpoint.
2. **El SELLER en `/users`: cerrado el 2026-10-01, ya no es una decisión abierta.** Se endurece
   respecto al Java — un SELLER recibe 403 en los tres endpoints que escriben. El razonamiento
   y las pruebas, en la nota del §5.
3. **`JWT_SECRET` tiene 13 bytes** y PyJWT avisa en cada firma (para HS256 el mínimo
   recomendado son 32). No se toca porque es **el mismo secreto que el backend Java en
   producción**: rotarlo obliga a cambiarlo a la vez en los dos, en los *secrets* de GitHub y
   en el VPS. **No silenciar el aviso.**
4. **El paso 14 tiene un problema nuevo desde que el repo es privado** (2026-09-20): el
   `git clone` anónimo que hacen los workflows de los otros proyectos **fallará**. Hará falta
   deploy key, PAT, o construir la imagen en CI y desplegar sólo la imagen, como hace
   `llm-gateway-resilience` con `ghcr.io`.
5. **El `CMD` del Dockerfile necesita el bucle de eventos correcto** (`--loop
   asyncio:SelectorEventLoop` o `python -m app.main`), o la conexión TLS a Aiven morirá con un
   `WinError 87` / `OperationalError (2003)` sin explicar por qué. Ver el comentario largo de
   `main.py`.

### Trampas ya pagadas — no volver a tropezar

- **`app.routes` no aplana los routers incluidos** en FastAPI 0.141.1 (sale un único
  `_IncludedRouter`). Para comprobar qué rutas hay: `app.openapi()["paths"]`.
- **`TestClient(app)` re-lanza la excepción no controlada** en vez de dejar que el handler
  genérico dé el 500. Hace falta `raise_server_exceptions=False`.
- **Una sola definición por dependencia.** `deps.py` importa de `core/`, nunca reimplementa:
  FastAPI cachea por identidad de función y dos `get_db` iguales-pero-distintos duplican las
  conexiones del pool (ver §8).
- **`ilike` no sirve de nada en MySQL** y quita el índice: la insensibilidad a mayúsculas la da
  la collation `utf8mb4_..._ci` de la columna.
- **Antes de dar por bueno un fichero, importarlo.** El bug recurrente del proyecto (cuatro
  veces ya) es llamar a una API plausible que nadie ha escrito: `from jose import`,
  `create_access_token(data=...)`, `app.api.dependencies.auth_deps` ×2. Un
  `python -c "import app.x.y"` lo caza en un segundo y leyendo no se ve.
- **Pero el import que funciona no demuestra nada.** En el paso 10 todo importaba y aun así
  `VentaCanceladaRepository` estaba en el fichero de ventas (segunda vez que pasa, tras
  `activity_log_service.py` en el paso 6). La comprobación que sí lo caza es mirar **qué hay en
  cada módulo**, no si se puede importar:
  `python -c "import app.x.y as m; print([n for n in dir(m) if not n.startswith('_')])"`.
  Un módulo vacío devuelve `[]` y una clase de más salta a la vista.
- **Rutas sin segmento: `""`, nunca `"/"`.** Con `prefix="/cancelaciones"`, `@router.get("")`
  da `/cancelaciones` y `@router.get("/")` da `/cancelaciones/`, que es otra ruta. La canónica
  tiene que ser la que llama el frontend, o se come un 307 en cada petición. En Spring,
  `@GetMapping` sin path sobre `@RequestMapping("/x")` es siempre `/x`.
- **Orden de declaración en rutas que colisionan.** Van dos prefijos con el mismo caso
  (`/users/all` vs `/users/{username}`, `/ventas/all` vs `/ventas/{username}`): la literal va
  **antes**. Y la forma de comprobarlo no es leer el fichero, es registrar a qué función del
  service llega la petición.
- **Cuidado al pegar tracebacks de pydantic**: los `ValidationError` incluyen el *valor* de
  entrada, y uno de ellos ya imprimió la contraseña de Aiven en claro.

---

---

## 11. El despliegue en AWS (paso 14) — hecho y desmontado el 2026-10-12

> **Desmontado el mismo 2026-10-12.** El ejercicio de AWS estaba hecho y el destino es Hetzner, asi que se termino la instancia y se borro todo (ECR, roles, proveedor OIDC). Comprobado en la consola: nada encendido. Esta seccion se queda como **receta y lecciones**, no como descripcion de algo vivo.

Decisión de Jabier: el destino no es Hetzner, sino **AWS**, como ejercicio práctico de cara a
entrevistas. Todo vive en **`eu-central-1` (Fráncfort)**.

**Por qué Fráncfort y no Virginia** (que era donde tenía cosas antes): se midió desde el VPS que
el MySQL de Aiven está en **Ámsterdam**, RTT 26 ms. Desde Virginia cada consulta serían ~85-95 ms
de ida y vuelta, y un endpoint con tres consultas se comería ~280 ms sólo en viajes.

### Las piezas

| Pieza | Nombre | Para qué |
|---|---|---|
| Registro de imágenes | `pharma-back-py`, `pharma-gpt-micro` (ECR privado) | la imagen que se despliega, con regla de ciclo de vida |
| Proveedor OIDC | `token.actions.githubusercontent.com` | que AWS se crea los carnés que firma GitHub |
| Rol para CI | `github-actions-pharma-ecr` | lo asume el workflow unos minutos: sólo subir imágenes a esos dos repositorios |
| Rol de instancia | `ec2-pharma-rol` | `AmazonEC2ContainerRegistryReadOnly` + `AmazonSSMManagedInstanceCore` |
| Máquina | `pharma-py`, t3.micro, Amazon Linux 2023 | Docker + compose + 1 GB de swap, instalados por el `user data` |
| Grupo de seguridad | `pharma-py-sg` | **sin reglas de entrada**: se entra por Session Manager |

**La idea que lo ordena todo: no hay una sola credencial guardada en ningún sitio.** GitHub firma
un carné temporal que dice qué repositorio y qué rama es; AWS lo verifica y presta el rol unos
minutos. La instancia pide sus credenciales por ser ella, y caducan solas. Si alguien se llevara
el disco de la máquina, no se llevaría nada reutilizable.

### La trampa del `sub` — tres ejecuciones perdidas

El workflow fallaba con `Not authorized to perform sts:AssumeRoleWithWebIdentity` con **todo
correcto**: proveedor, público `sts.amazonaws.com`, huella del certificado y ARN, comparados
carácter a carácter. La causa sólo apareció al volcar los campos del carné (nunca el token):

| | |
|---|---|
| Lo que exige el asistente de AWS | `repo:ko2javier/pharma_back_py:ref:refs/heads/master` |
| Lo que emite GitHub hoy | `repo:ko2javier@100034012/pharma_back_py@1374068965:ref:refs/heads/master` |

GitHub mete los **identificadores numéricos inmutables** de cuenta y repositorio. Es a propósito:
con sólo nombres, quien borra un repositorio y crea otro con el mismo nombre hereda la confianza.
La consola de AWS todavía genera el formato viejo. La condición del rol lleva ahora **las dos
formas**, con los IDs exactos y sin comodines.

**Regla que queda:** si AWS dice "no autorizado" en OIDC, el sospechoso es el `sub`, no la
política. Mirar el carné de verdad cuesta una ejecución.

### Lo demás que se aprendió escribiéndolo

- **No se construye la imagen en el servidor**, y eso resuelve dos cosas a la vez: el repositorio
  es privado (así la máquina no necesita acceso al código, sólo lectura en ECR) y tiene 1 GB de
  RAM (un `pip install` ahí dentro es candidato a morir por OOM).
- **`cache-to: type=gha` exige el driver `docker-container`**, que no es el de por defecto del
  runner: falta `docker/setup-buildx-action` y el build muere con `Cache export is not supported
  for the docker driver`. Sin caché habría funcionado: lo rompió la optimización.
- **Cada build de buildx crea tres entradas en ECR** (índice, capas y certificado de procedencia).
  Con una regla de ciclo de vida que cuenta imágenes, eso descuadra; se desactivó la procedencia
  con `provenance: false`.
- **`paths-ignore` para `**.md`**: un cambio de documentación no reconstruye la imagen. Es el
  problema que sí tiene el repo del back de Java.
- **Dos etiquetas por imagen**, `latest` y el SHA del commit. Sin la segunda no hay forma de
  saber qué código está corriendo ni a qué volver.

### Lo medido en la instancia

| Prueba | Resultado |
|---|---|
| `docker images` | 193 MB (65,79 comprimidos en ECR), digest idéntico al de ECR |
| `GET /` | 200 |
| `GET /users/all` sin token | 401 |
| `POST /auth/login` con usuario inventado | **401, no 500** — llegó a Aiven; el TLS con el `ca.pem` funciona desde AWS |
| `GET /docs` | 200 |
| Logs del contenedor | ninguna consulta SQL: `ENVIRONMENT=prod` llegó |
| RAM | 328 MB de 913, swap intacto — cabe el microservicio de IA al lado |

### Lo que queda abierto (ahora, para Hetzner)

1. **El despliegue sigue siendo manual**: el workflow sube la imagen a ECR, pero a la instancia hay que
   entrar por Session Manager y hacer `docker compose pull && up -d`. La vía limpia para
   automatizarlo es `ssm:SendCommand` desde Actions, sin abrir el 22 ni guardar claves. **Ese
   commit tiene que meter el repo en `REPOS_QUE_DESPLIEGAN` del `guard_push.py`.**
2. **El microservicio de IA no está en la instancia**: `/api/cima/validar` es el único de los 25
   que no funciona allí.
3. **El workflow no ejecuta los 195 tests.** Hoy es despliegue continuo, no CI/CD. Es el repo más
   barato donde arreglarlo: 1,6 s y sin base de datos.
4. **La regla temporal del puerto 8001** (HTTP sin cifrar, con el `JWT_SECRET` de producción
   detrás) hay que borrarla cuando no se use.

**Y lo que no hay que perder de vista:** esa instancia escribe en la **base de datos de
producción** y comparte el `JWT_SECRET` con el backend Java — comprobado, misma huella. No es un
entorno de pruebas.

---

**Entornos.** Este documento se escribió en el PC Linux, con un `.venv` de Python 3.12.3
(FastAPI 0.141.1, uvicorn 0.52.4, pydantic 2.13.5). En el PC Windows el proyecto vive en
`ko2-python-backends\pharma_back_py` y su `.venv` lo creó PyCharm con **Python 3.14.0**,
que no es la versión contra la que están fijadas las dependencias. Tenerlo presente si
`aiomysql` o `sqlalchemy` dan problemas al instalarse.

Pendiente: lo listado al final del §11.
