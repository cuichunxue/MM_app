FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY static/ static/
COPY app.py .

# SQLite の実体は /app/instance に置く(ボリュームで永続化すること)
VOLUME ["/app/instance"]

EXPOSE 8000

# SQLite は BEGIN IMMEDIATE + busy_timeout で書き込みを直列化しているため
# マルチワーカーでも安全。社内規模(〜数百人)なら 2 workers で十分
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "backend:create_app()"]
