"""
Shared Observability Library for AIOps Telemetry Platform
Provides unified metrics, tracing, and logging for all services.
"""

import os
import time
import uuid
import json
import logging
import threading
from datetime import datetime
from typing import Optional, Callable
from functools import wraps

import psutil
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from pythonjsonlogger import jsonlogger


# ============================================================================
# CONFIGURATION
# ============================================================================

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")
POD_ID = os.getenv("POD_ID", f"{SERVICE_NAME}-pod-{uuid.uuid4().hex[:8]}")
JAEGER_HOST = os.getenv("JAEGER_HOST", "jaeger")
JAEGER_PORT = int(os.getenv("JAEGER_PORT", "6831"))
VERSION = os.getenv("SERVICE_VERSION", "v1")


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# Request metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['service', 'method', 'endpoint'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

ERROR_COUNT = Counter(
    'errors_total',
    'Total errors',
    ['service', 'error_type']
)

# Resource metrics
CPU_USAGE = Gauge('cpu_usage_percent', 'CPU usage percentage', ['service', 'pod_id'])
MEMORY_USAGE = Gauge('memory_usage_mb', 'Memory usage in MB', ['service', 'pod_id'])
ERROR_RATE = Gauge('error_rate', 'Error rate (errors per second)', ['service'])

# Business metrics
ACTIVE_REQUESTS = Gauge('active_requests', 'Currently active requests', ['service'])


# ============================================================================
# STRUCTURED LOGGING
# ============================================================================

class TelemetryLogFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that includes trace context."""
    
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add standard fields
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        log_record['service_name'] = SERVICE_NAME
        log_record['pod_id'] = POD_ID
        log_record['version'] = VERSION
        
        # Add trace context if available
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            ctx = span.get_span_context()
            log_record['trace_id'] = format(ctx.trace_id, '032x')
            log_record['span_id'] = format(ctx.span_id, '016x')
        else:
            log_record['trace_id'] = ''
            log_record['span_id'] = ''


def setup_logging() -> logging.Logger:
    """Configure structured JSON logging."""
    logger = logging.getLogger(SERVICE_NAME)
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Console handler with JSON formatting
    handler = logging.StreamHandler()
    formatter = TelemetryLogFormatter(
        '%(timestamp)s %(service_name)s %(levelname)s %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


# ============================================================================
# DISTRIBUTED TRACING
# ============================================================================

def setup_tracing():
    """Configure OpenTelemetry tracing with Jaeger exporter."""
    resource = Resource.create({"service.name": SERVICE_NAME})
    
    provider = TracerProvider(resource=resource)
    
    try:
        jaeger_exporter = JaegerExporter(
            agent_host_name=JAEGER_HOST,
            agent_port=JAEGER_PORT,
        )
        provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
    except Exception as e:
        print(f"Warning: Could not connect to Jaeger: {e}")
    
    trace.set_tracer_provider(provider)
    return trace.get_tracer(SERVICE_NAME)


def get_tracer():
    """Get the current tracer."""
    return trace.get_tracer(SERVICE_NAME)


def get_current_trace_id() -> str:
    """Get the current trace ID as a hex string."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, '032x')
    return ""


def get_current_span_id() -> str:
    """Get the current span ID as a hex string."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().span_id, '016x')
    return ""


# ============================================================================
# METRICS COLLECTION
# ============================================================================

class MetricsCollector:
    """Collects and updates system metrics periodically."""
    
    def __init__(self, interval: float = 5.0):
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._error_count = 0
        self._request_count = 0
        self._last_error_rate_update = time.time()
    
    def start(self):
        """Start the metrics collection thread."""
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the metrics collection thread."""
        self._running = False
        if self._thread:
            self._thread.join()
    
    def record_error(self):
        """Record an error for rate calculation."""
        self._error_count += 1
    
    def record_request(self):
        """Record a request."""
        self._request_count += 1
    
    def _collect_loop(self):
        """Main collection loop."""
        while self._running:
            try:
                self._update_metrics()
            except Exception as e:
                print(f"Error collecting metrics: {e}")
            time.sleep(self.interval)
    
    def _update_metrics(self):
        """Update all system metrics."""
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=None)
        CPU_USAGE.labels(service=SERVICE_NAME, pod_id=POD_ID).set(cpu_percent)
        
        # Memory usage
        process = psutil.Process()
        memory_mb = process.memory_info().rss / (1024 * 1024)
        MEMORY_USAGE.labels(service=SERVICE_NAME, pod_id=POD_ID).set(memory_mb)
        
        # Error rate (errors per second over last interval)
        now = time.time()
        elapsed = now - self._last_error_rate_update
        if elapsed > 0:
            error_rate = self._error_count / elapsed
            ERROR_RATE.labels(service=SERVICE_NAME).set(error_rate)
            self._error_count = 0
            self._last_error_rate_update = now


# Global metrics collector
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


# ============================================================================
# FASTAPI MIDDLEWARE
# ============================================================================

def create_metrics_middleware(app):
    """Create middleware for automatic request instrumentation."""
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware
    
    class MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            start_time = time.time()
            ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
            
            try:
                response = await call_next(request)
                status = response.status_code
            except Exception as e:
                status = 500
                ERROR_COUNT.labels(service=SERVICE_NAME, error_type=type(e).__name__).inc()
                get_metrics_collector().record_error()
                raise
            finally:
                ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()
                duration = time.time() - start_time
                
                REQUEST_COUNT.labels(
                    service=SERVICE_NAME,
                    method=request.method,
                    endpoint=request.url.path,
                    status=status
                ).inc()
                
                REQUEST_LATENCY.labels(
                    service=SERVICE_NAME,
                    method=request.method,
                    endpoint=request.url.path
                ).observe(duration)
                
                get_metrics_collector().record_request()
            
            return response
    
    app.add_middleware(MetricsMiddleware)


def instrument_fastapi(app):
    """Instrument a FastAPI app with tracing."""
    FastAPIInstrumentor.instrument_app(app)


# ============================================================================
# FAILURE INJECTION
# ============================================================================

class FailureInjector:
    """Utilities for controlled failure injection."""
    
    @staticmethod
    def stress_cpu(duration_seconds: float = 5.0, intensity: float = 0.8):
        """
        Stress the CPU for a specified duration.
        
        Args:
            duration_seconds: How long to stress the CPU
            intensity: CPU usage target (0.0 to 1.0)
        """
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            # Busy work
            start = time.time()
            while time.time() - start < intensity * 0.1:
                _ = sum(i * i for i in range(10000))
            
            # Small sleep to control intensity
            time.sleep((1 - intensity) * 0.1)
    
    @staticmethod
    async def slow_response(delay_seconds: float = 2.0):
        """
        Introduce artificial latency.
        
        Args:
            delay_seconds: How long to delay the response
        """
        import asyncio
        await asyncio.sleep(delay_seconds)
    
    @staticmethod
    def trigger_error(error_type: str = "generic"):
        """
        Trigger a controlled error.
        
        Args:
            error_type: Type of error to trigger
        """
        errors = {
            "generic": Exception("Intentionally triggered error"),
            "thread_pool": Exception("Thread pool exhausted"),
            "cpu_throttle": Exception("CPU throttling detected"),
            "memory": MemoryError("Simulated memory exhaustion"),
            "timeout": TimeoutError("Simulated timeout"),
        }
        raise errors.get(error_type, errors["generic"])
    
    @staticmethod
    def simulate_memory_leak(size_mb: int = 10):
        """
        Simulate a memory leak by allocating and holding memory.
        
        Args:
            size_mb: Amount of memory to allocate in MB
        """
        # Store in global to prevent garbage collection
        global _leaked_memory
        if not hasattr(FailureInjector, '_leaked_memory'):
            FailureInjector._leaked_memory = []
        
        # Allocate specified MB of memory
        data = bytearray(size_mb * 1024 * 1024)
        FailureInjector._leaked_memory.append(data)
        
        return len(FailureInjector._leaked_memory) * size_mb
    
    @staticmethod
    def simulate_db_connection_loss(duration_seconds: float = 10.0):
        """
        Simulate a database connection loss.
        All database operations will fail until restored or duration expires.
        
        Args:
            duration_seconds: How long to block DB connections
        """
        from datetime import datetime, timedelta
        try:
            from database import FailureState
            FailureState.db_connection_blocked = True
            FailureState.db_failure_until = datetime.utcnow() + timedelta(seconds=duration_seconds)
            return {
                "status": "active",
                "type": "db_connection_loss",
                "duration_seconds": duration_seconds,
                "expires_at": FailureState.db_failure_until.isoformat()
            }
        except ImportError:
            # Fallback if database module not available
            return {
                "status": "error",
                "message": "Database module not available"
            }
    
    @staticmethod
    def simulate_redis_latency(delay_ms: int = 500, duration_seconds: float = 30.0):
        """
        Inject artificial latency into Redis operations.
        
        Args:
            delay_ms: Latency to add in milliseconds
            duration_seconds: How long to inject latency
        """
        from datetime import datetime, timedelta
        try:
            from database import FailureState
            FailureState.redis_latency_ms = delay_ms
            FailureState.redis_latency_until = datetime.utcnow() + timedelta(seconds=duration_seconds)
            return {
                "status": "active",
                "type": "redis_latency",
                "delay_ms": delay_ms,
                "duration_seconds": duration_seconds,
                "expires_at": FailureState.redis_latency_until.isoformat()
            }
        except ImportError:
            return {
                "status": "error",
                "message": "Database module not available"
            }
    
    @staticmethod
    def restore_db_connection():
        """
        Restore database connections after a simulated failure.
        """
        try:
            from database import FailureState
            FailureState.db_connection_blocked = False
            FailureState.db_failure_until = None
            return {"status": "restored", "type": "db_connection"}
        except ImportError:
            return {"status": "error", "message": "Database module not available"}
    
    @staticmethod
    def restore_redis_latency():
        """
        Remove Redis latency injection.
        """
        try:
            from database import FailureState
            FailureState.redis_latency_ms = 0
            FailureState.redis_latency_until = None
            return {"status": "restored", "type": "redis_latency"}
        except ImportError:
            return {"status": "error", "message": "Database module not available"}


# ============================================================================
# PROMETHEUS METRICS ENDPOINT
# ============================================================================

def get_metrics_response():
    """Generate Prometheus metrics response."""
    from fastapi.responses import Response
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# ============================================================================
# INITIALIZATION
# ============================================================================

def initialize_observability(app=None):
    """
    Initialize all observability components.
    
    Args:
        app: Optional FastAPI app to instrument
    
    Returns:
        Tuple of (logger, tracer, metrics_collector)
    """
    logger = setup_logging()
    tracer = setup_tracing()
    metrics = get_metrics_collector()
    metrics.start()
    
    if app:
        create_metrics_middleware(app)
        instrument_fastapi(app)
    
    # Instrument external HTTP calls
    HTTPXClientInstrumentor().instrument()
    
    logger.info(
        "Observability initialized",
        extra={
            "service_name": SERVICE_NAME,
            "pod_id": POD_ID,
            "version": VERSION,
            "jaeger_host": JAEGER_HOST
        }
    )
    
    return logger, tracer, metrics
