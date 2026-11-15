FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/ /app/backend/
COPY agents/ /app/agents/
COPY config/ /app/config/
COPY starter_kit/environment.py /app/starter_kit/environment.py
COPY starter_kit/battery_spec.json /app/starter_kit/battery_spec.json
RUN mkdir -p /app/data/train
COPY data/train/contador.csv data/train/inversor.csv data/train/precio_pvpc.csv data/train/co2_red.csv data/train/meteo.csv /app/data/train/
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
