# app/api/routes/router.py
#
# Este fichero es el equivalente de SecurityConfig.java: la tabla de qué exige
# cada prefijo, leída de arriba abajo. Consolidado aquí el 2026-10-04; antes
# cada controlador llevaba su propio dependencies=[...], y con las reglas
# repartidas por los ficheros no se veía de un vistazo qué estaba abierto — que
# es justo el agujero que apareció dos pasos seguidos (artículos en el 9 y
# users en el 9 bis).
#
# Equivalencia con el SecurityConfig del backend Java:
#
#   .requestMatchers("/auth/**").permitAll()           -> include_router(auth_router)  [sin dependencies]
#   .requestMatchers("/activity-log/**").hasRole(...)   -> dependencies=[Depends(require_role("SUPERADMIN"))]
#   .anyRequest().authenticated()                       -> dependencies=[Depends(get_current_user)]
#
# OJO, la diferencia que de verdad importa: en Spring, .anyRequest() es un
# CAJÓN DE SASTRE que cubre todo lo que no hayas listado antes, así que un
# @RestController nuevo nace protegido aunque te olvides de él. Aquí NO hay
# cajón de sastre: un include_router() sin dependencies nace ABIERTO. Por eso
# esta lista es la checklist obligatoria al cerrar cada paso.
from fastapi import APIRouter, Depends

# TU VERSIÓN: from app.api.routes import user_controller
# Importaba el MÓDULO, no el APIRouter que hay dentro. include_router() espera
# un APIRouter y un módulo no lo es: revienta al arrancar (ver abajo).
from app.api.routes.auth_controller import router as auth_router
from app.api.routes.articulo_controller import router as articulo_router
from app.api.routes.user_controller import router as user_router
from app.api.routes.activity_log_controller import router as activity_log_router
from app.api.deps import get_current_user, require_role

api_router = APIRouter()

# /auth/** -> PÚBLICO (permitAll).
# Si /auth/login exigiera token no habría forma de conseguir el primer token:
# el huevo y la gallina. /auth/protected sí valida el JWT, pero lo pide como
# parámetro dentro del propio controlador, no como gate del prefijo.
api_router.include_router(auth_router)

# /articulos/** -> AUTENTICADO.
# Sin esta línea los siete endpoints no existen, aunque el fichero esté
# escrito: es el equivalente a que Spring no escanee el @RestController. Un
# 404 de FastAPI y ninguna pista de por qué.
api_router.include_router(
    articulo_router,
    dependencies=[Depends(get_current_user)],
)

# /users/** -> AUTENTICADO.
# Las reglas finas (un ADMIN no modifica ni borra a otro ADMIN/SUPERADMIN; un
# SELLER no escribe) NO pueden estar aquí: dependen del rol del usuario
# OBJETIVO, no del que llama, así que viven en user_controller y registran un
# FORBIDDEN_ACTION en el activity_log antes de devolver el 403.
# TU VERSIÓN: api_router.include_router(user_controller)  <- el módulo
api_router.include_router(
    user_router,
    dependencies=[Depends(get_current_user)],
)

# /activity-log/** -> SOLO SUPERADMIN (hasRole("SUPERADMIN"), SecurityConfig:64).
# El único de los 25 endpoints que no es "autenticado" a secas, y el primer
# uso real de require_role en el proyecto.
#
# Dos detalles de la equivalencia que no son evidentes:
#
#   1. En Spring, hasRole("SUPERADMIN") compara contra la authority
#      ROLE_SUPERADMIN: el prefijo lo pone Spring por su cuenta. Aquí NO hay
#      prefijo que poner, porque require_role compara contra Users.permiso tal
#      cual está en la BD ("SUPERADMIN"). Si se escribiera "ROLE_SUPERADMIN"
#      no entraría nadie, y sin ruido: un 403 permanente.
#   2. require_role ya depende de get_current_user por dentro, así que esta
#      línea cubre también la autenticación. No hace falta añadir los dos: con
#      los dos, el 401 por falta de token sale igual, pero se declara dos veces
#      la misma dependencia.
api_router.include_router(
    activity_log_router,
    dependencies=[Depends(require_role("SUPERADMIN"))],
)
