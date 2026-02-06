"""
Deployment Tracker
Tracks service deployments (version changes, rollouts) and their results.
"""

import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional

# ============================================================================
# Configuration
# ============================================================================

DEPLOYMENT_LOG_FILE = os.getenv("DEPLOYMENT_LOG_FILE", "/data/deployments.json")


# ============================================================================
# Deployment Tracker
# ============================================================================

class DeploymentTracker:
    """Tracks service deployments."""
    
    def __init__(self, log_file: str = DEPLOYMENT_LOG_FILE):
        self.log_file = log_file
        self.deployments: List[Dict] = []
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Load existing deployments
        self._load_deployments()
    
    def _load_deployments(self):
        """Load existing deployments from file."""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    self.deployments = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load existing deployments: {e}")
            self.deployments = []
    
    def _save_deployments(self):
        """Save deployments to file."""
        try:
            with open(self.log_file, 'w') as f:
                json.dump(self.deployments, f, indent=2)
        except Exception as e:
            print(f"Error saving deployments: {e}")
    
    def record_deployment(
        self,
        service_name: str,
        version: str,
        result: str = "SUCCESS",
        incident_triggered_id: Optional[str] = None,
        details: str = ""
    ) -> Dict:
        """Record a deployment."""
        deployment_id = f"DEP-{uuid.uuid4().hex[:12].upper()}"
        
        deployment = {
            "deployment_id": deployment_id,
            "service_name": service_name,
            "version": version,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "result": result,
            "incident_triggered_id": incident_triggered_id or "",
            "details": details,
            "duration_seconds": None
        }
        
        self.deployments.append(deployment)
        self._save_deployments()
        
        print(f"[DEPLOYMENT] {deployment_id}: {service_name} {version} - {result}")
        return deployment
    
    def record_deployment_start(
        self,
        service_name: str,
        version: str
    ) -> Dict:
        """Record the start of a deployment (for tracking duration)."""
        return self.record_deployment(
            service_name=service_name,
            version=version,
            result="IN_PROGRESS",
            details="Deployment started"
        )
    
    def update_deployment_result(
        self,
        deployment_id: str,
        result: str,
        incident_triggered_id: Optional[str] = None,
        duration_seconds: Optional[float] = None
    ) -> Optional[Dict]:
        """Update the result of a deployment."""
        for deployment in self.deployments:
            if deployment["deployment_id"] == deployment_id:
                deployment["result"] = result
                if incident_triggered_id:
                    deployment["incident_triggered_id"] = incident_triggered_id
                if duration_seconds:
                    deployment["duration_seconds"] = duration_seconds
                self._save_deployments()
                return deployment
        return None
    
    def simulate_deployment(
        self,
        service_name: str,
        target_version: str,
        success_probability: float = 0.9
    ) -> Dict:
        """Simulate a deployment with configurable success rate."""
        import random
        import time
        
        # Start deployment
        deployment = self.record_deployment_start(service_name, target_version)
        
        # Simulate deployment time
        duration = random.uniform(5, 30)
        time.sleep(min(duration / 10, 0.5))  # Don't actually wait the full time
        
        # Determine result
        if random.random() < success_probability:
            result = "SUCCESS"
            incident_id = None
        else:
            result = "FAILED"
            incident_id = f"INC-{uuid.uuid4().hex[:12].upper()}"
        
        # Update deployment
        self.update_deployment_result(
            deployment["deployment_id"],
            result=result,
            incident_triggered_id=incident_id,
            duration_seconds=duration
        )
        
        return deployment
    
    def get_deployments(self, limit: int = 100) -> List[Dict]:
        """Get recent deployments."""
        return self.deployments[-limit:]
    
    def get_deployments_by_service(self, service_name: str) -> List[Dict]:
        """Get deployments for a specific service."""
        return [d for d in self.deployments if d["service_name"] == service_name]
    
    def get_failed_deployments(self) -> List[Dict]:
        """Get failed deployments."""
        return [d for d in self.deployments if d["result"] == "FAILED"]
    
    def get_deployments_csv_format(self) -> List[Dict]:
        """Get deployments in CSV-compatible format."""
        return [
            {
                "deployment_id": d["deployment_id"],
                "service_name": d["service_name"],
                "timestamp": d["timestamp"],
                "result": d["result"],
                "incident_triggered_id": d["incident_triggered_id"]
            }
            for d in self.deployments
        ]


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Deployment Tracker CLI")
    parser.add_argument("action", choices=["record", "list", "simulate"])
    parser.add_argument("--service", help="Service name")
    parser.add_argument("--version", help="Version")
    parser.add_argument("--result", default="SUCCESS", help="Deployment result")
    parser.add_argument("--count", type=int, default=5, help="Number of simulations")
    
    args = parser.parse_args()
    
    tracker = DeploymentTracker()
    
    if args.action == "record":
        if not args.service or not args.version:
            print("Error: --service and --version required")
            return
        
        deployment = tracker.record_deployment(
            service_name=args.service,
            version=args.version,
            result=args.result
        )
        print(f"Recorded: {deployment}")
    
    elif args.action == "list":
        deployments = tracker.get_deployments()
        for d in deployments:
            print(f"{d['deployment_id']}: {d['service_name']} {d.get('version', 'N/A')} - {d['result']}")
    
    elif args.action == "simulate":
        services = ["cart-service", "payment-service", "inventory-service"]
        versions = ["v1.0.0", "v1.1.0", "v1.2.0", "v2.0.0"]
        
        import random
        
        for i in range(args.count):
            service = random.choice(services)
            version = random.choice(versions)
            deployment = tracker.simulate_deployment(service, version)
            print(f"Simulated: {deployment['deployment_id']} - {deployment['result']}")


if __name__ == "__main__":
    main()
