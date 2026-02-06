# Build Images
docker build -t aiops/cart-service:latest -f services/cart-service/Dockerfile .
docker build -t aiops/payment-service:latest -f services/payment-service/Dockerfile .
docker build -t aiops/inventory-service:latest -f services/inventory-service/Dockerfile .
docker build -t aiops/frontend:latest ./frontend
docker build -t aiops/event-simulator:latest -f telemetry/Dockerfile.events .
docker build -t aiops/incident-tracker:latest -f telemetry/Dockerfile.incidents .

# Load into Kind (if using Kind)
Write-Host "Loading images into Kind cluster 'kind'..."
kind load docker-image aiops/cart-service:latest
kind load docker-image aiops/payment-service:latest
kind load docker-image aiops/inventory-service:latest
kind load docker-image aiops/frontend:latest
kind load docker-image aiops/event-simulator:latest
kind load docker-image aiops/incident-tracker:latest

Write-Host "Done! You can now run: kubectl apply -f k8s/"
