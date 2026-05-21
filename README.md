# Minimal URL Shortener

Este repositorio contiene un servicio minimalista de acortador de URL construido con FastAPI y Redis.

## Descripción

- `main.py` define una API con rutas principales:
  - `POST /shorten`: acorta una URL válida y la guarda en Redis.
  - `GET /{short_code}`: redirige a la URL original asociada con el código corto.
  - `GET /metrics`: expone métricas Prometheus.
  - `GET /health`: healthcheck de la aplicación y Redis.
- El servicio usa Redis para almacenar la relación `short_code -> url`.
- El código corto se genera con 6 caracteres alfanuméricos.

## Requisitos

- Python 3.12+
- Redis
- Docker y Docker Compose
- `pip` para instalar dependencias

## Dependencias

Instala las dependencias de la aplicación:

```bash
pip install -r requirements.txt
```

Instala dependencias de desarrollo para ejecutar los tests:

```bash
pip install -r requirements-dev.txt
```

## Variables de entorno

Copia `.env.example` a `.env` y ajusta los valores antes de iniciar los servicios:

```bash
cp .env.example .env
```

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `REDIS_URL` | URL de conexión a Redis (construida automáticamente en Compose) | `redis://localhost:6379` |
| `REDIS_PASSWORD` | Contraseña de autenticación de Redis | — |
| `GF_ADMIN_PASSWORD` | Contraseña del usuario `admin` de Grafana | — |

> **Nunca commits el archivo `.env` con credenciales reales.** Está incluido en `.gitignore`. Para CI/CD, define estas variables como secretos en tu plataforma (p. ej. GitHub Actions Secrets).

## Observabilidad

### Endpoints disponibles

- `GET /metrics`: métricas Prometheus.
- `GET /health`: healthcheck de la aplicación y conexión a Redis.

### Métricas expuestas

- `http_requests_total`
- `http_request_duration_seconds`
- `http_error_responses_total`
- `http_exceptions_total`
- `redis_errors_total`
- `app_info`
- métricas de proceso y plataforma de Prometheus.

## Arquitectura de observabilidad

1. `app` sirve la API y un endpoint `/metrics` para métricas de aplicación.
2. `redis-exporter` expone métricas específicas de Redis.
3. `node-exporter` recopila métricas del sistema de contenedor.
4. `prometheus` recolecta todas las métricas y las guarda.
5. `grafana` consume Prometheus para mostrar dashboards.

## Estructura recomendada de carpetas

```text
.
├── Dockerfile
├── docker-compose.yml
├── main.py
├── README.md
├── requirements.txt
├── requirements-dev.txt
├── prometheus/
│   └── prometheus.yml
├── grafana/
│   ├── dashboards/
│   │   └── url_shortener_dashboard.json
│   └── provisioning/
│       ├── dashboards/
│       │   └── dashboard.yml
│       └── datasources/
│           └── datasource.yml
└── tests/
    └── test_main.py
```

## Ejecución con Docker Compose

Arranca todos los servicios:

```bash
docker-compose up --build
```

Accede a:

- App: `http://localhost:8080`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (user: `admin`, password: valor de `GF_ADMIN_PASSWORD` en `.env`)

## Prometheus

Prometheus se configura en `prometheus/prometheus.yml` para scrapear:

- `app:8000` (`/metrics`)
- `redis-exporter:9121`
- `node-exporter:9100`

## Grafana

Grafana se configura con un datasource Prometheus y el dashboard provisionado en `grafana/dashboards/url_shortener_dashboard.json`.

## Pruebas

Ejecuta los tests con:

```bash
pytest
```

## Buenas prácticas

- Usa `docker-compose up --build` en entornos de desarrollo.
- Para producción, añade volúmenes persistentes y seguridad a Grafana.
- Habilita alertas en Prometheus cuando las métricas de errores o tiempo de respuesta excedan umbrales.
- Mantén `/health` y `/metrics` accesibles solo para sistemas de monitoreo.
- Controla la cardinalidad de las métricas en endpoints dinámicos.
