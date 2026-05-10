# Stub — D-1: tails Lobster Trap audit log, normalizes to SQLite ledger.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ledger_writer.py schema.sql ./
ENV LOBSTERTRAP_AUDIT_LOG=/data/lobstertrap-audit.log
ENV LEDGER_PATH=/data/diwan.db
CMD ["python", "ledger_writer.py"]
