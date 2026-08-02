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
# or lose the record of what has already been bought.
RUN mkdir -p /app/sessions /app/data && \
    useradd --create-home --uid 10001 tgmarket && \
    chown -R tgmarket:tgmarket /app
USER tgmarket

VOLUME ["/app/sessions", "/app/data"]

ENTRYPOINT ["python", "-m", "tgmarket"]
CMD ["run"]
