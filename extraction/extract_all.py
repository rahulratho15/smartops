#!/usr/bin/env python3
"""
AIOps Data Extraction Pipeline - Comprehensive Version
Extracts metrics, logs, traces, events, deployments, and incidents from Docker services
"""

import csv
import json
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor
import random
import time

# Configuration
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

SERVICES = {
    'cart-service': {'port': 8001, 'container': 'aiops-dataset-cart-service-1'},
    'payment-service': {'port': 8002, 'container': 'aiops-dataset-payment-service-1'},
    'inventory-service': {'port': 8003, 'container': 'aiops-dataset-inventory-service-1'},
    'frontend': {'port': 3000, 'container': 'aiops-dataset-frontend-1'},
}

PROMETHEUS_URL = 'http://localhost:9090'
JAEGER_URL = 'http://localhost:16686'

def get_timestamp():
    """Get current UTC timestamp in ISO format"""
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

# =============================================================================
# METRICS EXTRACTION - Enhanced with time series data
# =============================================================================

def extract_metrics():
    """Extract metrics from services and Prometheus with historical data"""
    print("\n📊 Extracting metrics from services...")
    metrics = []
    now = datetime.now(timezone.utc)
    
    # Get real-time metrics from each service
    for service_name, config in SERVICES.items():
        port = config['port']
        
        # 1. Get current metrics from /metrics endpoint
        try:
            start = time.time()
            response = requests.get(f'http://localhost:{port}/metrics', timeout=5)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                text = response.text
                
                # Parse Prometheus format metrics
                cpu_usage = 0
                memory_usage = 0
                error_rate = 0
                
                for line in text.split('\n'):
                    if line.startswith('process_cpu_seconds_total'):
                        try:
                            cpu_usage = float(line.split()[-1]) * 100
                        except:
                            pass
                    elif line.startswith('process_resident_memory_bytes'):
                        try:
                            memory_usage = float(line.split()[-1]) / (1024 * 1024)  # MB
                        except:
                            pass
                    elif 'http_requests_total' in line and 'status="5' in line:
                        try:
                            error_rate = float(line.split()[-1])
                        except:
                            pass
                
                metrics.append({
                    'timestamp': get_timestamp(),
                    'service_name': service_name,
                    'pod_id': f'{service_name.split("-")[0]}-pod-001',
                    'trace_id': '',
                    'cpu_usage': round(cpu_usage, 2),
                    'memory_usage': round(memory_usage, 2),
                    'latency_ms': round(latency_ms, 2),
                    'error_rate': round(error_rate, 4)
                })
        except Exception as e:
            print(f"  ⚠ Could not get metrics from {service_name}: {e}")
    
    # 2. Query Prometheus for historical metrics (last 5 minutes)
    prometheus_queries = [
        ('cpu_usage', 'rate(process_cpu_seconds_total[1m]) * 100'),
        ('memory_usage', 'process_resident_memory_bytes / 1024 / 1024'),
        ('http_request_duration', 'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m])) * 1000'),
    ]
    
    try:
        # Query range for last 5 minutes
        end_time = now.isoformat()
        start_time = (now - timedelta(minutes=5)).isoformat()
        
        for metric_name, query in prometheus_queries:
            try:
                response = requests.get(
                    f'{PROMETHEUS_URL}/api/v1/query_range',
                    params={
                        'query': query,
                        'start': start_time,
                        'end': end_time,
                        'step': '15s'
                    },
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'success' and data.get('data', {}).get('result'):
                        for result in data['data']['result']:
                            job = result.get('metric', {}).get('job', 'unknown')
                            for ts, value in result.get('values', []):
                                timestamp = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                                metrics.append({
                                    'timestamp': timestamp.isoformat().replace('+00:00', 'Z'),
                                    'service_name': job,
                                    'pod_id': f'{job.split("-")[0]}-pod-001' if '-' in job else 'unknown-pod',
                                    'trace_id': '',
                                    'cpu_usage': round(float(value), 2) if metric_name == 'cpu_usage' else 0,
                                    'memory_usage': round(float(value), 2) if metric_name == 'memory_usage' else 0,
                                    'latency_ms': round(float(value), 2) if metric_name == 'http_request_duration' else 0,
                                    'error_rate': 0
                                })
            except:
                pass
    except Exception as e:
        print(f"  ⚠ Prometheus query failed: {e}")
    
    # 3. Generate synthetic historical metrics if too few collected
    if len(metrics) < 100:
        print("  📈 Generating synthetic historical metrics...")
        for i in range(200):
            for service_name in SERVICES.keys():
                # Vary metrics based on time and add some anomalies
                is_anomaly = random.random() < 0.05  # 5% chance of anomaly
                
                base_cpu = random.uniform(5, 30)
                base_memory = random.uniform(50, 200)
                base_latency = random.uniform(10, 100)
                base_error = 0.0
                
                if is_anomaly:
                    anomaly_type = random.choice(['cpu_spike', 'memory_leak', 'high_latency', 'errors'])
                    if anomaly_type == 'cpu_spike':
                        base_cpu = random.uniform(80, 100)
                    elif anomaly_type == 'memory_leak':
                        base_memory = random.uniform(500, 1000)
                    elif anomaly_type == 'high_latency':
                        base_latency = random.uniform(2000, 10000)
                    elif anomaly_type == 'errors':
                        base_error = random.uniform(0.1, 0.5)
                
                timestamp = now - timedelta(minutes=i * 0.5)
                metrics.append({
                    'timestamp': timestamp.isoformat().replace('+00:00', 'Z'),
                    'service_name': service_name,
                    'pod_id': f'{service_name.split("-")[0]}-pod-001',
                    'trace_id': '',
                    'cpu_usage': round(base_cpu, 2),
                    'memory_usage': round(base_memory, 2),
                    'latency_ms': round(base_latency, 2),
                    'error_rate': round(base_error, 4)
                })
    
    # Write to CSV
    output_file = os.path.join(OUTPUT_DIR, 'metrics.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'service_name', 'pod_id', 'trace_id', 'cpu_usage', 'memory_usage', 'latency_ms', 'error_rate'])
        writer.writeheader()
        writer.writerows(metrics)
    
    print(f"  ✓ Written {len(metrics)} rows to {output_file}")
    return metrics

# =============================================================================
# LOGS EXTRACTION - Enhanced with better parsing
# =============================================================================

def extract_logs():
    """Extract logs from Docker containers with enhanced parsing"""
    print("\n📝 Extracting logs from containers...")
    logs = []
    
    for service_name, config in SERVICES.items():
        container = config['container']
        
        try:
            # Get last 1000 logs with timestamps
            result = subprocess.run(
                ['docker', 'logs', container, '--tail', '1000', '--timestamps'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            raw_output = result.stdout + result.stderr
            
            for line in raw_output.split('\n'):
                if not line.strip():
                    continue
                
                # Extract timestamp from Docker log format
                timestamp = get_timestamp()
                log_level = 'INFO'
                trace_id = ''
                log_message = line.strip()
                
                # Parse Docker timestamp (e.g., 2026-01-30T13:58:43.441243Z)
                docker_ts_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[.\d]*Z?)\s*(.*)', line)
                if docker_ts_match:
                    timestamp = docker_ts_match.group(1)
                    if not timestamp.endswith('Z'):
                        timestamp += 'Z'
                    log_message = docker_ts_match.group(2)
                
                # Detect log level
                msg_lower = log_message.lower()
                if any(x in msg_lower for x in ['error', '500', 'exception', 'failed', 'failure', 'traceback']):
                    log_level = 'ERROR'
                elif any(x in msg_lower for x in ['warn', 'warning']):
                    log_level = 'WARNING'
                elif any(x in msg_lower for x in ['debug']):
                    log_level = 'DEBUG'
                
                # Extract trace ID if present
                trace_match = re.search(r'trace[_-]?id[=:\s]+([a-f0-9]{32})', log_message, re.IGNORECASE)
                if trace_match:
                    trace_id = trace_match.group(1)
                
                logs.append({
                    'timestamp': timestamp,
                    'service_name': service_name,
                    'trace_id': trace_id,
                    'log_level': log_level,
                    'log_message': log_message[:500]  # Truncate long messages
                })
                
        except subprocess.TimeoutExpired:
            print(f"  ⚠ Timeout getting logs from {container}")
        except Exception as e:
            print(f"  ⚠ Error getting logs from {container}: {e}")
    
    # Write to CSV
    output_file = os.path.join(OUTPUT_DIR, 'logs.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'service_name', 'trace_id', 'log_level', 'log_message'])
        writer.writeheader()
        writer.writerows(logs)
    
    print(f"  ✓ Written {len(logs)} rows to {output_file}")
    return logs

# =============================================================================
# TRACES EXTRACTION - From Jaeger
# =============================================================================

def extract_traces():
    """Extract distributed traces from Jaeger"""
    print("\n🔗 Extracting traces from Jaeger...")
    traces = []
    
    services_to_query = ['cart-service', 'payment-service', 'inventory-service']
    
    for service in services_to_query:
        try:
            response = requests.get(
                f'{JAEGER_URL}/api/traces',
                params={
                    'service': service,
                    'limit': 500,
                    'lookback': '1h'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                for trace in data.get('data', []):
                    trace_id = trace.get('traceID', '')
                    
                    for span in trace.get('spans', []):
                        span_id = span.get('spanID', '')
                        parent_span_id = ''
                        
                        # Get parent span ID from references
                        for ref in span.get('references', []):
                            if ref.get('refType') == 'CHILD_OF':
                                parent_span_id = ref.get('spanID', '')
                        
                        # Get service name from process
                        process_id = span.get('processID', '')
                        processes = trace.get('processes', {})
                        span_service = processes.get(process_id, {}).get('serviceName', service)
                        
                        # Duration in ms
                        duration_ms = span.get('duration', 0) / 1000
                        
                        # Get status code from tags
                        status_code = 200
                        for tag in span.get('tags', []):
                            if tag.get('key') == 'http.status_code':
                                status_code = tag.get('value', 200)
                            elif tag.get('key') == 'error' and tag.get('value'):
                                status_code = 500
                        
                        traces.append({
                            'trace_id': trace_id,
                            'span_id': span_id,
                            'parent_span_id': parent_span_id,
                            'service_name': span_service,
                            'duration_ms': round(duration_ms, 3),
                            'status_code': status_code
                        })
                        
        except Exception as e:
            print(f"  ⚠ Could not get traces for {service}: {e}")
    
    # Write to CSV
    output_file = os.path.join(OUTPUT_DIR, 'traces.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['trace_id', 'span_id', 'parent_span_id', 'service_name', 'duration_ms', 'status_code'])
        writer.writeheader()
        writer.writerows(traces)
    
    print(f"  ✓ Written {len(traces)} rows to {output_file}")
    return traces

# =============================================================================
# K8S EVENTS EXTRACTION - Enhanced from logs and health checks
# =============================================================================

def extract_k8s_events(logs):
    """Extract Kubernetes-like events from logs and service health"""
    print("\n📋 Extracting events...")
    events = []
    now = datetime.now(timezone.utc)
    
    # 1. Get container creation events from Docker
    for service_name, config in SERVICES.items():
        container = config['container']
        port = config['port']
        pod_name = f'{service_name.split("-")[0]}-pod-{port}'
        
        try:
            result = subprocess.run(
                ['docker', 'inspect', container, '--format', '{{.Created}}'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                created_time = result.stdout.strip()
                events.append({
                    'timestamp': created_time if 'T' in created_time else get_timestamp(),
                    'resource_name': pod_name,
                    'reason': 'Created',
                    'message': f'Created container {service_name}'
                })
                events.append({
                    'timestamp': created_time if 'T' in created_time else get_timestamp(),
                    'resource_name': pod_name,
                    'reason': 'Started',
                    'message': f'Started container {service_name}'
                })
        except:
            pass
        
        # 2. Check current health status
        try:
            response = requests.get(f'http://localhost:{port}/health', timeout=5)
            status = 'healthy' if response.status_code == 200 else 'unhealthy'
            events.append({
                'timestamp': get_timestamp(),
                'resource_name': pod_name,
                'reason': 'HealthCheck',
                'message': f'Service {service_name} is {status}'
            })
        except:
            events.append({
                'timestamp': get_timestamp(),
                'resource_name': pod_name,
                'reason': 'HealthCheckFailed',
                'message': f'Health check failed for {service_name}'
            })
    
    # 3. Extract events from logs (errors, warnings, restarts)
    error_patterns = [
        (r'500 Internal Server Error', 'Error', 'HTTP 500 error'),
        (r'connection refused', 'ConnectionError', 'Connection refused'),
        (r'timeout', 'Timeout', 'Request timeout'),
        (r'out of memory', 'OOMKilled', 'Out of memory'),
        (r'memory leak', 'Warning', 'Memory leak detected'),
        (r'cpu stress', 'Warning', 'High CPU usage'),
        (r'exception|traceback', 'Error', 'Exception occurred'),
    ]
    
    seen_events = set()
    for log in logs:
        if log['log_level'] == 'ERROR':
            log_msg = log['log_message'].lower()
            service = log['service_name']
            
            for pattern, reason, message in error_patterns:
                if re.search(pattern, log_msg, re.IGNORECASE):
                    # Avoid duplicate events
                    event_key = f"{service}_{reason}_{log['timestamp'][:16]}"
                    if event_key not in seen_events:
                        seen_events.add(event_key)
                        events.append({
                            'timestamp': log['timestamp'],
                            'resource_name': f'{service.split("-")[0]}-pod-{SERVICES.get(service, {}).get("port", "000")}',
                            'reason': reason,
                            'message': f'{message} in {service}'
                        })
                    break
    
    # 4. Generate synthetic scaling events
    for i in range(5):
        ts = (now - timedelta(minutes=random.randint(5, 60))).isoformat().replace('+00:00', 'Z')
        service = random.choice(list(SERVICES.keys()))
        events.append({
            'timestamp': ts,
            'resource_name': f'{service.split("-")[0]}-pod-{SERVICES[service]["port"]}',
            'reason': random.choice(['Scaled', 'Pulling', 'Pulled']),
            'message': random.choice([
                f'Scaled up replica count to 2',
                f'Pulling image for {service}',
                f'Successfully pulled image'
            ])
        })
    
    # Sort by timestamp
    events.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Write to CSV
    output_file = os.path.join(OUTPUT_DIR, 'k8s_events.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'resource_name', 'reason', 'message'])
        writer.writeheader()
        writer.writerows(events)
    
    print(f"  ✓ Written {len(events)} rows to {output_file}")
    return events

# =============================================================================
# DEPLOYMENTS EXTRACTION - Enhanced with history
# =============================================================================

def extract_deployments():
    """Extract deployment information from Docker containers"""
    print("\n🚀 Extracting deployments...")
    deployments = []
    now = datetime.now(timezone.utc)
    
    for service_name, config in SERVICES.items():
        container = config['container']
        
        try:
            result = subprocess.run(
                ['docker', 'inspect', container],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data:
                    container_info = data[0]
                    created = container_info.get('Created', get_timestamp())
                    
                    # Current deployment
                    deployments.append({
                        'deployment_id': f'DEP-{random.randint(100000, 999999)}',
                        'service_name': service_name,
                        'timestamp': created,
                        'result': 'SUCCESS',
                        'incident_triggered_id': ''
                    })
        except:
            pass
    
    # Generate synthetic historical deployments
    for i in range(10):
        ts = (now - timedelta(days=random.randint(1, 30))).isoformat().replace('+00:00', 'Z')
        service = random.choice(list(SERVICES.keys()))
        result = 'SUCCESS' if random.random() > 0.1 else 'FAILED'
        incident_id = f'INC-{random.randint(1000, 9999)}' if result == 'FAILED' else ''
        
        deployments.append({
            'deployment_id': f'DEP-{random.randint(100000, 999999)}',
            'service_name': service,
            'timestamp': ts,
            'result': result,
            'incident_triggered_id': incident_id
        })
    
    # Sort by timestamp
    deployments.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Write to CSV
    output_file = os.path.join(OUTPUT_DIR, 'deployments.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['deployment_id', 'service_name', 'timestamp', 'result', 'incident_triggered_id'])
        writer.writeheader()
        writer.writerows(deployments)
    
    print(f"  ✓ Written {len(deployments)} rows to {output_file}")
    return deployments

# =============================================================================
# INCIDENTS EXTRACTION - Enhanced detection from logs and traces
# =============================================================================

def extract_incidents(logs, traces):
    """Extract incidents from error patterns in logs and traces"""
    print("\n🚨 Extracting incidents...")
    incidents = []
    now = datetime.now(timezone.utc)
    
    # Pattern-based incident detection from logs
    incident_patterns = {
        'http_500': {
            'pattern': r'500 internal server error|status.*500',
            'failure_type': 'http_500_error'
        },
        'timeout': {
            'pattern': r'timeout|timed out',
            'failure_type': 'timeout_error'
        },
        'connection': {
            'pattern': r'connection refused|connection error|connect failed',
            'failure_type': 'connection_error'
        },
        'memory': {
            'pattern': r'out of memory|memory leak|oom',
            'failure_type': 'memory_error'
        },
        'cpu': {
            'pattern': r'cpu stress|high cpu|cpu spike',
            'failure_type': 'cpu_stress'
        },
        'exception': {
            'pattern': r'exception|traceback|error:',
            'failure_type': 'application_error'
        }
    }
    
    # Track incidents by service and time window (5-minute buckets)
    incident_buckets = {}
    
    for log in logs:
        if log['log_level'] in ['ERROR', 'WARNING']:
            log_msg = log['log_message'].lower()
            service = log['service_name']
            
            for incident_type, config in incident_patterns.items():
                if re.search(config['pattern'], log_msg, re.IGNORECASE):
                    # Create time bucket (5-minute window)
                    try:
                        log_time = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00'))
                        bucket_key = (service, incident_type, log_time.strftime('%Y-%m-%dT%H:%M')[:-1] + '0')
                        
                        if bucket_key not in incident_buckets:
                            incident_buckets[bucket_key] = {
                                'start_time': log['timestamp'],
                                'end_time': log['timestamp'],
                                'service': service,
                                'failure_type': config['failure_type'],
                                'count': 0
                            }
                        
                        incident_buckets[bucket_key]['end_time'] = log['timestamp']
                        incident_buckets[bucket_key]['count'] += 1
                    except:
                        pass
                    break
    
    # Convert to incident records
    for bucket_key, data in incident_buckets.items():
        if data['count'] >= 1:  # At least 1 error in the bucket
            incidents.append({
                'incident_id': f'INC-{random.randint(10000, 99999)}',
                'start_time': data['start_time'],
                'end_time': data['end_time'],
                'root_cause_service': data['service'],
                'failure_type': data['failure_type']
            })
    
    # Check traces for errors (status_code != 200)
    trace_errors = {}
    for trace in traces:
        if trace['status_code'] != 200:
            service = trace['service_name']
            key = (service, trace['trace_id'][:8])  # Group by trace prefix
            
            if key not in trace_errors:
                trace_errors[key] = {
                    'service': service,
                    'status_code': trace['status_code']
                }
    
    for key, data in trace_errors.items():
        incidents.append({
            'incident_id': f'INC-{random.randint(10000, 99999)}',
            'start_time': get_timestamp(),
            'end_time': get_timestamp(),
            'root_cause_service': data['service'],
            'failure_type': f'http_{data["status_code"]}_error'
        })
    
    # Generate synthetic incidents if none found
    if len(incidents) < 5:
        print("  📊 Generating synthetic incidents for training data...")
        failure_types = [
            'memory_leak', 'cpu_spike', 'http_500_error', 'timeout_error',
            'connection_refused', 'thread_pool_exhausted', 'disk_full',
            'database_connection_error', 'authentication_failure', 'rate_limited'
        ]
        
        for i in range(20):
            start = now - timedelta(hours=random.randint(1, 72))
            duration = timedelta(minutes=random.randint(5, 60))
            
            incidents.append({
                'incident_id': f'INC-{random.randint(10000, 99999)}',
                'start_time': start.isoformat().replace('+00:00', 'Z'),
                'end_time': (start + duration).isoformat().replace('+00:00', 'Z'),
                'root_cause_service': random.choice(list(SERVICES.keys())),
                'failure_type': random.choice(failure_types)
            })
    
    # Sort by start time
    incidents.sort(key=lambda x: x['start_time'], reverse=True)
    
    # Write to CSV  
    output_file = os.path.join(OUTPUT_DIR, 'incidents.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['incident_id', 'start_time', 'end_time', 'root_cause_service', 'failure_type'])
        writer.writeheader()
        writer.writerows(incidents)
    
    print(f"  ✓ Written {len(incidents)} rows to {output_file}")
    return incidents

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("AIOps Data Extraction Pipeline - Comprehensive Version")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    
    # Extract all data types
    metrics = extract_metrics()
    logs = extract_logs()
    traces = extract_traces()
    events = extract_k8s_events(logs)
    deployments = extract_deployments()
    incidents = extract_incidents(logs, traces)
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ Extraction complete! Summary:")
    print("=" * 60)
    print(f"  📊 Metrics:     {len(metrics):,} rows")
    print(f"  📝 Logs:        {len(logs):,} rows")
    print(f"  🔗 Traces:      {len(traces):,} rows")
    print(f"  📋 Events:      {len(events):,} rows")
    print(f"  🚀 Deployments: {len(deployments):,} rows")
    print(f"  🚨 Incidents:   {len(incidents):,} rows")
    print(f"\nTotal records:  {len(metrics) + len(logs) + len(traces) + len(events) + len(deployments) + len(incidents):,}")
    print(f"Output files in: {OUTPUT_DIR}")
    print("=" * 60)

if __name__ == '__main__':
    main()
