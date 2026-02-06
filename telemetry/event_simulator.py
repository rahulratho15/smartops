"""
Kubernetes-like Event Simulator
Simulates K8s events (BackOff, OOMKill, Unhealthy) for testing and telemetry.
"""

import os
import json
import time
import random
import threading
from datetime import datetime
from typing import List, Dict

# ============================================================================
# Configuration
# ============================================================================

EVENT_LOG_FILE = os.getenv("EVENT_LOG_FILE", "/data/k8s_events.json")
SIMULATION_INTERVAL = int(os.getenv("SIMULATION_INTERVAL", "30"))  # seconds

# Services to simulate events for
SERVICES = [
    {"name": "cart-service", "pod_prefix": "cart-pod"},
    {"name": "payment-service", "pod_prefix": "payment-pod"},
    {"name": "inventory-service", "pod_prefix": "inventory-pod"},
]

# Event templates
EVENT_TEMPLATES = [
    {
        "reason": "BackOff",
        "message_template": "Back-off restarting failed container {container} in pod {pod}",
        "severity": "Warning",
        "probability": 0.1
    },
    {
        "reason": "OOMKilled",
        "message_template": "Container {container} in pod {pod} was OOM Killed",
        "severity": "Warning",
        "probability": 0.05
    },
    {
        "reason": "Unhealthy",
        "message_template": "Readiness probe failed: HTTP probe failed with statuscode: 503",
        "severity": "Warning", 
        "probability": 0.15
    },
    {
        "reason": "Pulled",
        "message_template": "Successfully pulled image \"{image}\"",
        "severity": "Normal",
        "probability": 0.2
    },
    {
        "reason": "Created",
        "message_template": "Created container {container}",
        "severity": "Normal",
        "probability": 0.2
    },
    {
        "reason": "Started",
        "message_template": "Started container {container}",
        "severity": "Normal",
        "probability": 0.3
    },
    {
        "reason": "Killing",
        "message_template": "Stopping container {container}",
        "severity": "Normal",
        "probability": 0.05
    },
    {
        "reason": "FailedScheduling",
        "message_template": "0/3 nodes are available: 3 Insufficient cpu.",
        "severity": "Warning",
        "probability": 0.02
    },
]


# ============================================================================
# Event Generator
# ============================================================================

class EventSimulator:
    """Simulates Kubernetes-like events."""
    
    def __init__(self, log_file: str = EVENT_LOG_FILE):
        self.log_file = log_file
        self.events: List[Dict] = []
        self._running = False
        self._thread = None
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Load existing events
        self._load_events()
    
    def _load_events(self):
        """Load existing events from file."""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    self.events = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load existing events: {e}")
            self.events = []
    
    def _save_events(self):
        """Save events to file."""
        try:
            with open(self.log_file, 'w') as f:
                json.dump(self.events, f, indent=2)
        except Exception as e:
            print(f"Error saving events: {e}")
    
    def generate_event(self, service: Dict = None, event_template: Dict = None) -> Dict:
        """Generate a single event."""
        if service is None:
            service = random.choice(SERVICES)
        
        if event_template is None:
            event_template = random.choice(EVENT_TEMPLATES)
        
        pod_id = f"{service['pod_prefix']}-{random.randint(1000, 9999)}"
        container_name = service['name'].replace('-service', '')
        
        message = event_template['message_template'].format(
            container=container_name,
            pod=pod_id,
            image=f"aiops/{service['name']}:latest"
        )
        
        event = {
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "resource_name": pod_id,
            "resource_kind": "Pod",
            "namespace": "default",
            "reason": event_template['reason'],
            "message": message,
            "severity": event_template['severity'],
            "service": service['name']
        }
        
        self.events.append(event)
        self._save_events()
        
        return event
    
    def generate_failure_event(self, service_name: str, reason: str, message: str):
        """Generate a specific failure event."""
        event = {
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "resource_name": f"{service_name.replace('-service', '')}-pod-{random.randint(1000, 9999)}",
            "resource_kind": "Pod",
            "namespace": "default",
            "reason": reason,
            "message": message,
            "severity": "Warning",
            "service": service_name
        }
        
        self.events.append(event)
        self._save_events()
        
        print(f"[EVENT] {reason}: {message}")
        return event
    
    def start_simulation(self, interval: int = SIMULATION_INTERVAL):
        """Start background event simulation."""
        self._running = True
        self._thread = threading.Thread(target=self._simulation_loop, args=(interval,))
        self._thread.daemon = True
        self._thread.start()
        print(f"Event simulator started (interval: {interval}s)")
    
    def stop_simulation(self):
        """Stop the simulation."""
        self._running = False
        if self._thread:
            self._thread.join()
    
    def _simulation_loop(self, interval: int):
        """Main simulation loop."""
        while self._running:
            # Randomly decide whether to generate an event
            for template in EVENT_TEMPLATES:
                if random.random() < template['probability']:
                    event = self.generate_event(event_template=template)
                    print(f"[SIMULATED EVENT] {event['reason']}: {event['message'][:50]}...")
            
            time.sleep(interval)
    
    def get_events(self, limit: int = 100) -> List[Dict]:
        """Get recent events."""
        return self.events[-limit:]
    
    def get_events_csv_format(self) -> List[Dict]:
        """Get events in CSV-compatible format."""
        return [
            {
                "timestamp": e["timestamp"],
                "resource_name": e["resource_name"],
                "reason": e["reason"],
                "message": e["message"]
            }
            for e in self.events
        ]


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    simulator = EventSimulator()
    
    print("Starting K8s Event Simulator...")
    print(f"Events will be written to: {EVENT_LOG_FILE}")
    
    # Generate initial events
    for _ in range(5):
        event = simulator.generate_event()
        print(f"Generated: {event['reason']} - {event['message'][:50]}")
    
    # Start continuous simulation
    simulator.start_simulation()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping simulator...")
        simulator.stop_simulation()
