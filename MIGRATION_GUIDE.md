# Upgrade Guide: Production-Grade AIOps Environment

This guide details the upgrades made to transform the environment into a realistic AIOps target, addressing identified gaps.

## 1. Trace Propagation Fixed
**Code Change**: Updated `services/shared/observability.py` to instrument `httpx`.
**Impact**: Distributed traces will now properly show the full path `Frontend -> Cart -> Payment -> Inventory`. No more broken trace graphs.

## 2. Realistic Traffic Generation
**New Tool**: Added `locustfile.py`.
**Usage**:
1. Install locust: `pip install locust`
2. Run load test: `locust -f locustfile.py --host http://localhost:3000`
3. Access UI: http://localhost:8089 to control user load.
**Impact**: Generates sustained, realistic user sessions (browsing, adding to cart, checkout) instead of simple "ping" scripts.

## 3. Kubernetes Migration
**New Artifacts**: `k8s/` directory containing full manifests.
**Why**: Moves from Docker Compose to real orchestration.
**How to Deploy**:
```powershell
# 1. Prerequisite: Install Kind (Kubernetes in Docker)
# choco install kind

# 2. Create Cluster
kind create cluster --name aiops

# 3. Build & Load Images
./build_k8s_images.ps1

# 4. Apply Manifests
kubectl apply -f k8s/

# 5. Access Frontend
kubectl port-forward svc/frontend 3000:3000
```

## 4. Chaos Mesh (Advanced Faults)
To achieve "Real K8s Signals" (Pod Kill, Network Loss), install Chaos Mesh:

```bash
# Install with Helm
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh --create-namespace --version 2.6.2
```

Use Dashboard: http://localhost:2333

## Summary of Changes
- **Observability**: `httpx` instrumented.
- **Traffic**: Locust added.
- **Infrastructure**: K8s manifests generated.
- **Signals**: Real K8s events now possible via Kind + Chaos Mesh.
