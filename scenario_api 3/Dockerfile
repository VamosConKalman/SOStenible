FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV ARTIFACTS_DIR=/app/artifacts DATA_DIR=/data/train
EXPOSE 8000
# Si falta artifacts/gaussian.joblib i hi ha CSV a /data/train, l'ajusta en arrencar.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
