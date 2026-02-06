#  SmartOps AI - Target Application

> **Production-Grade Microservices Demo Environment for Autonomous Incident Resolution**

A fully instrumented e-commerce microservices application designed as a **target system** for training and demonstrating AI-powered incident response engines. Built with real persistence (PostgreSQL + Redis), comprehensive observability (Prometheus + Jaeger), and built-in chaos engineering capabilities.

![Architecture](https://img.shields.io/badge/Architecture-Microservices-blue)
![Observability](https://img.shields.io/badge/Observability-OpenTelemetry-orange)
![Database](https://img.shields.io/badge/Database-PostgreSQL%20%2B%20Redis-green)
![Python](https://img.shields.io/badge/Python-3.11-yellow)

---

##  Project Purpose

This application serves as a **realistic target environment** for:

| Use Case | Description |
|----------|-------------|
| **AIOps Training** | Generate real metrics, logs, and traces for ML model training |
| **Incident Simulation** | Built-in failure injection for testing auto-remediation |
| **Observability Demo** | Showcase Prometheus, Jaeger, and structured logging integration |
| **Chaos Engineering** | Test system resilience with controlled failures |

---

##  Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (:3000)                         │
│                     TechStore Pro - Nginx                        │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ Cart Service│   │   Payment   │   │  Inventory  │
│   :8001     │──▶│   Service   │──▶│   Service   │
│             │   │    :8002    │   │    :8003    │
└──────┬──────┘   └─────────────┘   └──────┬──────┘
       │                                    │
       ▼                                    ▼
┌─────────────┐                    ┌─────────────┐
│    Redis    │                    │ PostgreSQL  │
│   (Carts)   │                    │ (Products/  │
│    :6379    │                    │   Orders)   │
└─────────────┘                    │    :5432    │
                                   └─────────────┘
          │
          └────────────── Observability Stack ──────────────┐
                                                            │
                    ┌─────────────┐   ┌─────────────┐       │
                    │ Prometheus  │   │   Jaeger    │       │
                    │   :9090     │   │   :16686    │◀──────┘
                    └─────────────┘   └─────────────┘
```

---

##  Project Structure

```
smartops/
├── 📂 services/
│   ├── 📂 shared/                  # Shared libraries
│   │   ├── observability.py        # Metrics, logging, tracing, failure injection
│   │   ├── database.py             # PostgreSQL + Redis clients
│   │   └── requirements.txt        # Python dependencies
│   │
│   ├── 📂 cart-service/            # Shopping cart management
│   │   ├── main.py                 # FastAPI app (Redis carts, PostgreSQL orders)
│   │   └── Dockerfile
│   │
│   ├── 📂 payment-service/         # Payment processing
│   │   ├── main.py                 # FastAPI app with inventory integration
│   │   └── Dockerfile
│   │
│   └── 📂 inventory-service/       # Product inventory
│       ├── main.py                 # FastAPI app (PostgreSQL persistence)
│       └── Dockerfile
│
├── 📂 frontend/                    # TechStore Pro UI
│   ├── index.html                  # Main HTML
│   ├── app.js                      # JavaScript with admin chaos panel
│   ├── styles.css                  # Styling
│   └── Dockerfile                  # Nginx container
│
├── 📂 telemetry/                   # Telemetry simulators
│   ├── event_simulator.py          # K8s-like event generation
│   ├── incident_tracker.py         # Auto incident detection
│   └── deployment_tracker.py       # Deployment tracking
│
├── 📂 k8s/                         # Kubernetes manifests
│   ├── 01-observability.yaml       # Prometheus + Jaeger
│   └── 02-services.yaml            # Microservices
│
├── 📂 extraction/                  # Data extraction tools
│   └── extract_all.py              # Export metrics/logs/traces
│
├── docker-compose.yml              # Local orchestration
├── prometheus.yml                  # Prometheus config
└── locustfile.py                   # Load testing
```

---

##  Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Web Framework** | FastAPI | Async Python microservices |
| **Database** | PostgreSQL 16 | Persistent storage (products, orders) |
| **Cache** | Redis 7 | Session storage (shopping carts) |
| **Metrics** | Prometheus | Time-series metrics collection |
| **Tracing** | Jaeger + OpenTelemetry | Distributed request tracing |
| **Logging** | Structured JSON | LLM-parseable log format |
| **Frontend** | Nginx + Vanilla JS | Static file serving |
| **Orchestration** | Docker Compose / K8s | Container management |

---

##  Quick Start

### Prerequisites
- Docker & Docker Compose
- 4GB RAM minimum

### Run Locally

```bash
# Clone the repository
git clone https://github.com/rahulratho15/smartops.git
cd smartops

# Start all services
docker-compose up -d

# Wait for initialization (30 seconds)
# Then access the application
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://localhost:3000 | TechStore Pro UI |
| **Prometheus** | http://localhost:9090 | Metrics dashboard |
| **Jaeger** | http://localhost:16686 | Distributed traces |
| **Cart API** | http://localhost:8001/docs | Cart service Swagger |
| **Payment API** | http://localhost:8002/docs | Payment service Swagger |
| **Inventory API** | http://localhost:8003/docs | Inventory service Swagger |

---

##  Observability Features

### Metrics (Prometheus)
Each service exposes `/metrics` endpoint with:
- `http_requests_total` - Request count by endpoint/method/status
- `http_request_duration_seconds` - Latency histogram
- `memory_usage_mb` - Real memory consumption
- `cpu_usage_percent` - CPU utilization
- `error_rate` - Error rate per service
- `active_requests` - Current concurrent requests

### Logs (Structured JSON)
```json
{
  "timestamp": "2026-02-06T12:00:00.000Z",
  "service_name": "cart-service",
  "pod_id": "cart-pod-001",
  "trace_id": "abc123...",
  "span_id": "def456...",
  "level": "INFO",
  "message": "Checkout completed",
  "order_id": "ORD-123",
  "total": 999.99
}
```

### Traces (OpenTelemetry → Jaeger)
- Full request flow visualization
- Cross-service span propagation
- Database and Redis call instrumentation

---

##  Chaos Engineering

### Built-in Failure Injection Endpoints

| Endpoint | Effect | Example |
|----------|--------|---------|
| `POST /stress-cpu` | CPU spike | `{"duration": 10, "intensity": 0.9}` |
| `POST /slow-response` | Add latency | `{"delay": 5.0}` |
| `POST /trigger-error` | Force errors | `{"error_type": "timeout"}` |
| `POST /memory-leak` | Memory allocation | `{"size_mb": 50}` |
| `POST /simulate-db-failure` | Block DB | `{"duration": 30}` |
| `POST /simulate-redis-latency` | Redis delay | `{"delay_ms": 500}` |

### PowerShell Examples
```powershell
# Simulate database outage for 30 seconds
Invoke-RestMethod -Uri "http://localhost:8001/simulate-db-failure" `
  -Method POST -ContentType "application/json" `
  -Body '{"duration": 30}'

# Inject Redis latency
Invoke-RestMethod -Uri "http://localhost:8001/simulate-redis-latency" `
  -Method POST -ContentType "application/json" `
  -Body '{"delay_ms": 500, "duration": 60}'
```

---

##  Database Schema

### PostgreSQL Tables

**products**
| Column | Type | Description |
|--------|------|-------------|
| item_id | VARCHAR(50) PK | Product identifier |
| name | VARCHAR(200) | Product name |
| price | FLOAT | Unit price |
| quantity | INT | Stock count |

**orders**
| Column | Type | Description |
|--------|------|-------------|
| order_id | VARCHAR(50) PK | Order identifier |
| user_id | VARCHAR(100) | Customer ID |
| total_amount | FLOAT | Order total |
| payment_id | VARCHAR(50) | Payment reference |
| status | VARCHAR(50) | Order status |

**order_items**
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Auto-increment ID |
| order_id | VARCHAR(50) FK | Parent order |
| item_id | VARCHAR(50) | Product ID |
| quantity | INT | Quantity ordered |
| unit_price | FLOAT | Price at purchase |

### Redis Keys
- `cart:{user_id}` - Shopping cart JSON (1hr TTL)

---

##  Testing

### Load Testing with Locust
```bash
pip install locust
locust -f locustfile.py --host=http://localhost:8001
# Open http://localhost:8089 for Locust UI
```

### API Testing (PowerShell)
```powershell
# Add to cart
Invoke-RestMethod -Uri "http://localhost:8001/cart/add" `
  -Method POST -ContentType "application/json" `
  -Body '{"user_id":"test","item_id":"PROD-001","quantity":2}'

# Checkout
Invoke-RestMethod -Uri "http://localhost:8001/cart/checkout" `
  -Method POST -ContentType "application/json" `
  -Body '{"user_id":"test"}'

# View orders
Invoke-RestMethod -Uri "http://localhost:8001/orders/test"
```

---

##  View Database Data

```bash
# View orders
docker exec aiops-postgres psql -U aiops -d aiops -c "SELECT * FROM orders;"

# View products
docker exec aiops-postgres psql -U aiops -d aiops -c "SELECT * FROM products;"

# View Redis carts
docker exec aiops-redis redis-cli KEYS "cart:*"
```

---

##  Prometheus Queries

```promql
# Total requests by service
sum by (service) (http_requests_total)

# Request latency 95th percentile
histogram_quantile(0.95, http_request_duration_seconds_bucket)

# Memory usage
memory_usage_mb

# Error rate
error_rate
```

---

##  Development

### Add New Service
1. Create `services/new-service/main.py`
2. Import shared `observability.py` and `database.py`
3. Add Dockerfile
4. Update `docker-compose.yml`
5. Update `prometheus.yml` scrape targets

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | postgres | Database host |
| `POSTGRES_PORT` | 5432 | Database port |
| `REDIS_HOST` | redis | Cache host |
| `JAEGER_HOST` | jaeger | Tracing backend |

---



**Built for SmartOps AI - Autonomous Incident Resolution Engine** 
