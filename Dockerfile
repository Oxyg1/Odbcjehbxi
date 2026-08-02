FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps -e .

# Session and ledger live on a volume so a rebuild does not force a re-login
# or lose the record of what has already been bought. Bind-mounted host
# directories take their ownership from the host, not from an image-time
# chown, so a non-root container user reliably can't write them unless the
# host directories are pre-chowned to match every deployment - not something
# worth asking of a single-tenant personal bot. Run as root in the container
# instead; this only ever runs on its own VPS, not multi-tenant infra.
RUN mkdir -p /app/sessions /app/data

VOLUME ["/app/sessions", "/app/data"]

ENTRYPOINT ["python", "-m", "tgmarket"]
CMD ["run"]
