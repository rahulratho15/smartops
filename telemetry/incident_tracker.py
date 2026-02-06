"""
Incident Tracker
Detects and tracks incidents based on error rates, latency, and deployment failures.
"""

import os
import json
import time
import uuid
import threading
from datetime import datetime
from typing import List, Dict, Optional

import httpx

# ============================================================================
# Configuration
# ============================================================================

INCIDENT_LOG_FILE = os.getenv("INCIDENT_LOG_FILE", "/data/incidents.json")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10"))  # seconds

# Service endpoints for health/metrics checks
SERVICES = {
    "cart-service": os.getenv("CART_SERVICE_URL", "http://cart-service:8001"),
    "payment-service": os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8002"),
    "inventory-service": os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8003"),
}

# Thresholds for incident detection
THRESHOLDS = {
    "error_rate": 0.1,  # 10% error rate triggers incident
    "latency_ms": 5000,  # 5 second latency triggers incident
    "consecutive_failures": 3,  # 3 consecutive health check failures
}


# ============================================================================
# Incident Tracker
# ============================================================================

class IncidentTracker:
    """Tracks and manages incidents."""
    
    def __init__(self, log_file: str = INCIDENT_LOG_FILE):
        self.log_file = log_file
        self.incidents: List[Dict] = []
        self.active_incidents: Dict[str, Dict] = {}  # service -> incident
        self.failure_counts: Dict[str, int] = {}  # service -> consecutive failures
        self._running = False
        self._thread = None
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Load existing incidents
        self._load_incidents()
    
    def _load_incidents(self):
        """Load existing incidents from file."""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    self.incidents = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load existing incidents: {e}")
            self.incidents = []
    
    def _save_incidents(self):
        """Save incidents to file."""
        try:
            with open(self.log_file, 'w') as f:
                json.dump(self.incidents, f, indent=2)
        except Exception as e:
            print(f"Error saving incidents: {e}")
    
    def create_incident(
        self,
        service: str,
        failure_type: str,
        details: str = ""
    ) -> Dict:
        """Create a new incident."""
        incident_id = f"INC-{uuid.uuid4().hex[:12].upper()}"
        
        incident = {
            "incident_id": incident_id,
            "start_time": datetime.utcnow().isoformat() + 'Z',
            "end_time": None,
            "root_cause_service": service,
            "failure_type": failure_type,
            "status": "active",
            "details": details,
            "triggered_by": "auto_detection"
        }
        
        self.incidents.append(incident)
        self.active_incidents[service] = incident
        self._save_incidents()
        
        print(f"[INCIDENT CREATED] {incident_id}: {failure_type} on {service}")
        return incident
    
    def resolve_incident(self, service: str) -> Optional[Dict]:
        """Resolve an active incident for a service."""
        if service not in self.active_incidents:
            return None
        
        incident = self.active_incidents[service]
        incident["end_time"] = datetime.utcnow().isoformat() + 'Z'
        incident["status"] = "resolved"
        
        del self.active_incidents[service]
        self._save_incidents()
        
        print(f"[INCIDENT RESOLVED] {incident['incident_id']}")
        return incident
    
    def create_deployment_incident(
        self,
        service: str,
        deployment_id: str,
        failure_reason: str
    ) -> Dict:
        """Create an incident triggered by a failed deployment."""
        incident_id = f"INC-{uuid.uuid4().hex[:12].upper()}"
        
        incident = {
            "incident_id": incident_id,
            "start_time": datetime.utcnow().isoformat() + 'Z',
            "end_time": None,
            "root_cause_service": service,
            "failure_type": "deployment_failure",
            "status": "active",
            "details": f"Deployment {deployment_id} failed: {failure_reason}",
            "triggered_by": deployment_id
        }
        
        self.incidents.append(incident)
        self.active_incidents[service] = incident
        self._save_incidents()
        
        print(f"[DEPLOYMENT INCIDENT] {incident_id} triggered by {deployment_id}")
        return incident
    
    async def check_service_health(self, service: str, url: str) -> Dict:
        """Check health of a service."""
        result = {
            "service": service,
            "healthy": False,
            "latency_ms": None,
            "error": None
        }
        
        try:
            start = time.time()
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{url}/health", timeout=10.0)
                latency = (time.time() - start) * 1000
                
                result["latency_ms"] = latency
                result["healthy"] = response.status_code == 200
                
                if latency > THRESHOLDS["latency_ms"]:
                    result["high_latency"] = True
                    
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def process_health_result(self, result: Dict):
        """Process a health check result and create/resolve incidents."""
        service = result["service"]
        
        if result["healthy"] and not result.get("high_latency"):
            # Service is healthy
            self.failure_counts[service] = 0
            
            # Resolve any active incident
            if service in self.active_incidents:
                self.resolve_incident(service)
        else:
            # Service has issues
            self.failure_counts[service] = self.failure_counts.get(service, 0) + 1
            
            if self.failure_counts[service] >= THRESHOLDS["consecutive_failures"]:
                # Create incident if not already active
                if service not in self.active_incidents:
                    failure_type = "high_latency" if result.get("high_latency") else "service_unavailable"
                    details = result.get("error") or f"Latency: {result.get('latency_ms')}ms"
                    self.create_incident(service, failure_type, details)
    
    def start_monitoring(self, interval: int = CHECK_INTERVAL):
        """Start background health monitoring."""
        self._running = True
        self._thread = threading.Thread(target=self._monitoring_loop, args=(interval,))
        self._thread.daemon = True
        self._thread.start()
        print(f"Incident tracker started (interval: {interval}s)")
    
    def stop_monitoring(self):
        """Stop monitoring."""
        self._running = False
        if self._thread:
            self._thread.join()
    
    def _monitoring_loop(self, interval: int):
        """Main monitoring loop."""
        import asyncio
        
        async def check_all():
            for service, url in SERVICES.items():
                result = await self.check_service_health(service, url)
                self.process_health_result(result)
        
        while self._running:
            try:
                asyncio.run(check_all())
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
            
            time.sleep(interval)
    
    def get_incidents(self, limit: int = 100) -> List[Dict]:
        """Get recent incidents."""
        return self.incidents[-limit:]
    
    def get_active_incidents(self) -> List[Dict]:
        """Get currently active incidents."""
        return list(self.active_incidents.values())
    
    def get_incidents_csv_format(self) -> List[Dict]:
        """Get incidents in CSV-compatible format."""
        return [
            {
                "incident_id": i["incident_id"],
                "start_time": i["start_time"],
                "end_time": i["end_time"] or "",
                "root_cause_service": i["root_cause_service"],
                "failure_type": i["failure_type"]
            }
            for i in self.incidents
        ]


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    tracker = IncidentTracker()
    
    print("Starting Incident Tracker...")
    print(f"Incidents will be written to: {INCIDENT_LOG_FILE}")
    
    # Start monitoring
    tracker.start_monitoring()
    
    try:
        while True:
            # Print status periodically
            active = tracker.get_active_incidents()
            if active:
                print(f"Active incidents: {len(active)}")
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nStopping tracker...")
        tracker.stop_monitoring()
