FROM python:3.11-slim

WORKDIR /app

# Optimizamos el cache de pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway ignora EXPOSE, pero es buena práctica dejarlo 
# o usar la variable de entorno directamente en el CMD
EXPOSE 8000

# La clave es usar sh -c para que la variable $PORT se expanda correctamente
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]