# build context is the repo root (see docker-compose.yml) -- backend/ imports ml/
FROM python:3.12-slim
WORKDIR /app

# libgomp1 (OpenMP runtime) is needed by lightgbm's compiled library -- python:slim
# strips it out by default
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ml/ ml/
COPY backend/ backend/

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
