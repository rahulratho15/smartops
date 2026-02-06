FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/shared/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy shared modules
COPY services/shared/observability.py /app/observability.py
COPY services/shared/database.py /app/database.py

# Copy service code
COPY services/inventory-service/main.py /app/main.py

# Set environment variables
ENV SERVICE_NAME=inventory-service
ENV PYTHONUNBUFFERED=1

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
