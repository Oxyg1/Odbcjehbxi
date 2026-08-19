FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ (SQLite DB + log file) is meant to be mounted as a volume so it
# survives container restarts/rebuilds -- see docker-compose.yml.
VOLUME ["/app/data"]

CMD ["python", "bot.py"]
