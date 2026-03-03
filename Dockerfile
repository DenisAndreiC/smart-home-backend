FROM python:3.13-slim

WORKDIR /app

# Instalăm dependențele mai întâi (layer cacheabil)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiem tot codul sursă
COPY . .

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
