# Dockerfile — imagen de produccion de la API.
#
# Equivale al Dockerfile del backend Java, pero sin etapa de build: Python no
# compila nada, asi que no hace falta el patron de dos etapas
# (maven -> jre). Lo que si se hace es copiar solo lo necesario para ejecutar.

# La MISMA version que el .venv local. Si aqui pusiera 3.13 y en local tienes
# 3.14, un fallo de version solo aparece en produccion. Comprobado
# construyendo: las 10 dependencias de requirements.txt se instalan por
# wheels, sin compilador y sin paquetes del sistema. Imagen final: 281 MB.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001

WORKDIR /app

# El requirements va SOLO y ANTES que el codigo: Docker cachea cada linea, y
# asi cambiar un controlador no reinstala las dependencias. Al reves, cada
# despliegue costaria el pip install entero.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# requirements-dev.txt NO entra: pytest no pinta nada en produccion. Es el
# <scope>test</scope> del pom.xml.
COPY app/ ./app/

# El ca.pem SI entra, y es imprescindible: Aiven firma con una CA propia y sin
# ese fichero la conexion muere con CERTIFICATE_VERIFY_FAILED. No es un
# secreto (es un certificado publico, cero claves privadas) y por eso esta
# versionado en el repositorio.
COPY ca.pem .

# El .env NO entra nunca (ver .dockerignore): en produccion las variables las
# pone docker-compose. Una imagen con credenciales dentro es una imagen que no
# se puede publicar en ningun registro.

# Usuario sin privilegios, como el "spring" del Dockerfile del Java. Si
# alguien llegara a ejecutar codigo aqui, lo haria como easyfarma y no como
# root. El chown va ANTES del USER porque despues ya no habria permisos.
RUN addgroup --system easyfarma && adduser --system --group easyfarma && \
    chown -R easyfarma:easyfarma /app
USER easyfarma:easyfarma

EXPOSE 8001

# El CMD, que es donde esta todo lo delicado:
#
#  * sh -c + exec. Se podria poner la forma exec pura
#    (CMD ["uvicorn", "--port", "8001", ...]), pero entonces el puerto estaria
#    escrito dos veces: aqui y en la variable PORT que Settings exige. Con
#    ${PORT} hay una sola fuente. El "exec" es lo que hace que uvicorn
#    SUSTITUYA al shell y reciba el SIGTERM de "docker stop": sin el, el shell
#    se queda de PID 1, no reenvia la senal, y cada parada tarda 10 s y acaba
#    en SIGKILL.
#
#  * --host 0.0.0.0. En main.py es 127.0.0.1 porque alli es para el PC; dentro
#    del contenedor, 127.0.0.1 no seria accesible desde fuera.
#
#  * --loop asyncio:SelectorEventLoop. El --help dice [auto|asyncio|uvloop],
#    pero uvicorn acepta tambien una ruta de importacion: comprobado dentro de
#    la imagen, arranca. En Linux "asyncio" ya ES el selector, asi que aqui no
#    cambia nada; se escribe completo para que sea la MISMA linea en Windows y
#    en el VPS y para que no se pierda el motivo — el ProactorEventLoop de
#    Windows no sabe hacer el paso a TLS a mitad de conexion que exige MySQL, y
#    la conexion a Aiven muere con un WinError 87 que no dice nada.
#    Efecto secundario que conviene saber: con esto NO se usa uvloop, que es lo
#    que elegiria "auto". Se cambia un poco de velocidad por correccion.
#
#  * --proxy-headers ya viene activado por defecto, pero se escribe porque sin
#    el la IP del activity_log seria la del proxy. Su companero,
#    FORWARDED_ALLOW_IPS, NO va aqui: es una variable de entorno y vive en el
#    docker-compose, donde se cambia sin reconstruir la imagen. Medido con una
#    peticion con X-Forwarded-For: 83.45.12.7
#        sin FORWARDED_ALLOW_IPS -> la API ve 172.17.0.1 (el proxy)
#        con FORWARDED_ALLOW_IPS=* -> la API ve 83.45.12.7 (el navegador)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --loop asyncio:SelectorEventLoop --proxy-headers"]
