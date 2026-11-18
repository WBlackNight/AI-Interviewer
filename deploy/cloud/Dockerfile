FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /srv/app app \
    && mkdir -p /srv/app /srv/state \
    && chown -R 10001:10001 /srv/app /srv/state

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /srv/app
COPY --chown=10001:10001 backend/app ./backend/app
COPY --chown=10001:10001 data ./data
COPY --chown=10001:10001 assets ./assets
COPY --chown=10001:10001 ui ./ui
COPY --chown=10001:10001 tools ./tools
COPY --chown=10001:10001 evals ./evals
COPY --chown=10001:10001 *.html ./

USER 10001:10001
WORKDIR /srv/app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"

# Only Caddy can reach this port. Proxy headers are not accepted on a public app port.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log", "--timeout-graceful-shutdown", "25"]
