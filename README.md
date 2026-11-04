# Mundial Docker

Repositorio público: https://github.com/gabrielharo-dotcom/mundial-docker

[Informe Word con arquitectura y capturas reales de Docker](docs/Informe_laboratorio_Mundial_Docker_GitHub.docx) · [Video de la funcionalidad sin narración](docs/Demostracion_funcional_Mundial.mp4)

Aplicación académica local para pronósticos de fútbol, sin apuestas. Python 3.12 o posterior, sin paquetes externos para ejecutar la aplicación o sus pruebas. Los encuentros y resultados precargados son ficticios.

## Inicio local en Windows

Abra PowerShell dentro de esta carpeta:

```powershell
python run_local.py --demo
```

Abra http://127.0.0.1:8080. Cuenta: `ana@demo.local`, contraseña: `Mundial2026!`. Otros usuarios de demostración: `luis@demo.local`, `sofia@demo.local`, `diego@demo.local`, con la misma contraseña. Código de invitación: `MUNDIAL-DEMO`.

El iniciador ejecuta tres procesos API en los puertos 8001, 8002 y 8003 y un balanceador round robin en 8080. Ctrl+C detiene los cuatro procesos. Los puertos deben estar libres. La base persiste en `data/mundial.db`; omita `--demo` para iniciar sin generar datos. El comando de demo es idempotente y no restablece partidos ya existentes. No inicie a la vez el modo local y Docker porque comparten el puerto 8080.

## Docker Compose

Requiere Docker Engine con contenedores Linux y Docker Compose. Se instaló y verificó Docker Engine 29.9.3 con Compose 5.7.0 en Ubuntu 24.04 sobre WSL 2. Se construyeron las imágenes, se iniciaron tres réplicas con Nginx, se escaló a cinco y se regresó a tres. El ensayo final sobre Docker completó 4 000 solicitudes sin errores. Las pruebas nativas de Windows se conservan por separado.

En este equipo, desde PowerShell en la carpeta del proyecto, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\DOCKER_LAB.ps1 -Action up -Replicas 3
powershell -ExecutionPolicy Bypass -File .\DOCKER_LAB.ps1 -Action status
# Para escalar:
powershell -ExecutionPolicy Bypass -File .\DOCKER_LAB.ps1 -Action up -Replicas 5
# Para detener conservando el volumen:
powershell -ExecutionPolicy Bypass -File .\DOCKER_LAB.ps1 -Action down
```

El iniciador detecta Docker nativo o usa Ubuntu-24.04 en WSL. En WSL mantiene una sesión de trabajo en segundo plano mientras se usa la aplicación: los servicios systemd no mantienen por sí solos la distribución encendida. Esta medida resolvió una interrupción observada durante el primer ensayo; su registro se conserva en `evidence/docker/stress-initial-interrupted.json`.

Un segundo ensayo detectó saturación de la cola de conexiones: el servidor HTTP tenía una cola predeterminada de 5. Se amplió a 256 y se ajustaron los intentos de Nginx a tres fallos antes de retirar una réplica. La respuesta de éxito se envía después de confirmar la transacción SQLite. El registro previo al ajuste está en `evidence/docker/stress-initial-backlog.json`; los resultados finales corresponden al montaje corregido.

Si usa una terminal Linux con Docker, o Docker Desktop desde Windows, los comandos equivalentes son:

```powershell
docker compose config
docker compose up --build -d --scale app=3
docker compose ps
docker compose logs --no-color
1..12 | ForEach-Object { (Invoke-RestMethod http://127.0.0.1:8080/health).instance }
docker compose up -d --scale app=5
docker compose ps
docker compose down
```

Nginx 1.28 resuelve `app` mediante DNS de Docker y reparte las conexiones entre las direcciones del servicio. No se fija `container_name` ni se publican puertos individuales de app, lo que permite escalar. `init` genera datos antes del inicio de las réplicas. El volumen local `lab-data` conserva base, usuarios y sesiones al detener o recrear contenedores. `docker compose down` conserva ese volumen. No ejecute `down -v` si necesita los datos.

Para repetir las evidencias Docker: `powershell -ExecutionPolicy Bypass -File .\verify_docker.ps1`. La verificación detecta Docker nativo o Docker en Ubuntu-24.04, inicia tres réplicas y las deja activas para inspección. Los registros originales y seis capturas reales están en `evidence/docker/`. Las capturas del visor de registros muestran salidas auténticas de Docker CLI, sin imitar la interfaz de Docker Desktop.

## Funcionalidad

1. Regístrese o inicie sesión. Las contraseñas usan PBKDF2 SHA256 con sal individual. Las sesiones tienen caducidad de 24 horas y se guardan en la base compartida.
2. Cree una sala o entre con código o enlace `/?invite=CODIGO`. El enlace se procesa después del inicio de sesión.
3. El creador agrega partidos con hora futura. Las horas se guardan como Unix UTC y el navegador las muestra en su zona local.
4. Cada miembro registra o edita un marcador antes del inicio. La última edición define el instante usado para anticipación. Goles válidos: enteros de 0 a 30.
5. El creador publica o corrige resultados después del inicio, una vez terminado el encuentro. No existe modo que permita anticipar resultados por API. Los resultados históricos del demo se insertan con el script de fixtures.
6. El ranking y el desglose se recalculan desde los resultados para evitar duplicar puntos al corregir. Use Actualizar para ver cambios realizados por otros participantes.

## Acuerdos de puntuación

- Exacto: 5 puntos base, sin sumar otra vez ganador y diferencia.
- Sin exacto: 3 por ganador o empate y 2 si la diferencia con signo es igual. Ejemplo 3-1 frente a 2-0: 5 puntos base. Un empate 2-2 frente a 1-1 también suma 5 porque ambas diferencias son cero.
- Cada tercer acierto consecutivo de ganador/empate añade 2: partidos 3, 6, 9 de una racha. Un fallo o ausencia la reinicia.
- Más de 86400 segundos antes: +1 incluso sin acertar. Exactamente 24 horas, o 10 minutos antes: sin bono. No hay penalización adicional por último minuto; se acepta hasta antes del inicio.
- Orden: inicio del partido y luego ID. Si falta publicar un resultado, el cálculo se detiene en ese punto hasta resolverlo, para mantener estable la definición de consecutivos.
- El marcador corresponde al tiempo reglamentario y su descuento; se excluyen penales y prórroga. Los partidos eliminatorios pueden tener empate en este criterio.
- Desempate: puntos, exactos, aciertos e ID de usuario ascendente.

Estas decisiones resuelven ambigüedades del enunciado y están declaradas también en el informe. No se añadieron estadísticas con IA, que eran opcionales.

## Verificación reproducible

```powershell
python -m unittest discover -s tests -v
python verify_cluster.py
# Con run_local.py --demo o Docker funcionando en 8080:
python stress.py
```

La suite crea una base temporal y comprueba 29 casos de puntuación, tiempos, autorización, aislamiento y persistencia lógica. `verify_cluster.py` usa puertos 8101 a 8103 y 8180, crea una base temporal, detiene una réplica, la recupera y reinicia todas. Sus procesos terminan automáticamente. `stress.py` utiliza la cuenta de demo, calienta el sistema y ejecuta 100, 300, 600 y 1000 peticiones por modo con concurrencias 1, 10, 50 y 100. Modifica repetidamente el pronóstico del primer partido futuro de Ana: es un ensayo de contención sobre una misma fila. Si ya no quedan partidos futuros, agregue uno desde la interfaz.

`evidence/stress.json`, `cluster.json`, `ui.json`, `tests.txt` y los PNG contienen resultados medidos y capturas. La prueba UI automatizada se ejecutó con Playwright y Edge; no es una dependencia de la aplicación. El equipo de carga y el servidor fueron el mismo equipo: las cifras no representan capacidad de nube.

`evidence/stress-docker.json` corresponde a la carga sobre Nginx y los contenedores Linux. `evidence/docker/routing.json` conserva el reparto de 30 solicitudes entre tres réplicas y de 50 entre cinco, además de la conservación de sesión y pronóstico después de reiniciar las réplicas. Los HTML de esa carpeta son visores de los registros de texto y JSON utilizados para las capturas.

Para repetir la prueba UI opcional, con Node.js, Edge y el servidor activo, instale Playwright con `npm install --no-save playwright` y ejecute `node tests/ui.cjs`. El ensayo crea una cuenta nueva, la une al demo, crea otra sala y actualiza las capturas. Para que las capturas muestren exactamente cuatro usuarios iniciales se necesita una base de demostración recién generada. La aplicación funciona sin npm ni Playwright.

## Estructura y arquitectura

- `app.py`: servidor HTTP, autorización, API, almacenamiento y puntuación.
- `static/`: cliente HTML, CSS y JavaScript.
- `proxy.py`: balanceador local con failover al fallar la conexión.
- `run_local.py`: inicio de tres réplicas y el balanceador.
- `seed_demo.py`: datos ficticios reproducibles.
- `Dockerfile`, `compose.yaml`, `nginx.conf`: despliegue con volumen compartido y DNS dinámico.
- `DOCKER_LAB.ps1`: inicio, estado, escalamiento y parada desde Windows con Docker nativo o WSL 2.
- `tests/`, `stress.py`, `verify_cluster.py`: pruebas reproducibles.

Cada petición usa una conexión SQLite independiente, claves foráneas y espera de bloqueo de 20 s. Se usa el diario rollback predeterminado de SQLite, no WAL. `BEGIN IMMEDIATE` serializa las escrituras de predicciones y resultados. Las restricciones únicas impiden pronósticos duplicados y membresías duplicadas. Las consultas usan parámetros y el cliente escapa el texto antes de insertarlo en HTML.

El escalamiento horizontal demostrado replica la capa de aplicación dentro de un solo host. SQLite compartido no permite escalar este diseño a varios hosts y serializa escrituras. Nginx, el host y la base son puntos únicos de falla. Para producción harían falta PostgreSQL como servicio, servidor HTTP de producción, TLS, límites de solicitudes, limpieza de sesiones, políticas de contraseñas y monitoreo. Este laboratorio queda vinculado solo a localhost.

## Fuentes técnicas

- Docker Compose, redes y escalamiento: https://docs.docker.com/compose/how-tos/networking/
- Docker Compose up: https://docs.docker.com/reference/cli/docker/compose/up/
- Nginx upstream y resolución dinámica: https://nginx.org/en/docs/http/ngx_http_upstream_module.html
- Python sqlite3: https://docs.python.org/3.14/library/sqlite3.html
- Transacciones y bloqueos SQLite: https://www.sqlite.org/lockingv3.html
- Docker Engine en Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- Ciclo de vida de servicios systemd en WSL: https://learn.microsoft.com/en-us/windows/wsl/systemd
