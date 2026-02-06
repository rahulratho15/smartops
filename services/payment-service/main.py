"""
Payment Service - AIOps Telemetry Platform
Handles payment processing with full observability instrumentation.
"""

import os
import uuid
import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from observability import (
    initialize_observability,
    get_metrics_response,
    FailureInjector,
    get_tracer,
    get_current_trace_id,
    SERVICE_NAME,
    POD_ID,
    VERSION
)

# ============================================================================
# CONFIGURATION
# ============================================================================

INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8003")


# ============================================================================
# MODELS
# ============================================================================

class PaymentRequest(BaseModel):
    order_id: str
    item_id: str
    quantity: int
    amount: float
    payment_method: str = "credit_card"


class PaymentResponse(BaseModel):
    success: bool
    payment_id: str
    order_id: str
    amount: float
    status: str
    trace_id: str
    message: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    pod_id: str
    version: str
    timestamp: str


class FailureRequest(BaseModel):
    duration: Optional[float] = 5.0
    intensity: Optional[float] = 0.8
    delay: Optional[float] = 2.0
    error_type: Optional[str] = "generic"
    size_mb: Optional[int] = 10


# ============================================================================
# APPLICATION SETUP
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Payment service starting", extra={"event": "startup"})
    yield
    logger.info("Payment service shutting down", extra={"event": "shutdown"})


app = FastAPI(
    title="Payment Service",
    description="Handles payment processing for AIOps Telemetry Platform",
    version=VERSION,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize observability
logger, tracer, metrics = initialize_observability(app)


# ============================================================================
# HEALTH & METRICS ENDPOINTS
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        pod_id=POD_ID,
        version=VERSION,
        timestamp=datetime.utcnow().isoformat() + 'Z'
    )


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return get_metrics_response()


# ============================================================================
# BUSINESS ENDPOINTS
# ============================================================================

@app.post("/payment/process", response_model=PaymentResponse)
async def process_payment(request: PaymentRequest):
    """
    Process a payment for an order.
    This will also reserve inventory from the inventory service.
    """
    payment_id = f"PAY-{uuid.uuid4().hex[:12].upper()}"
    
    with tracer.start_as_current_span("process_payment") as span:
        span.set_attribute("payment_id", payment_id)
        span.set_attribute("order_id", request.order_id)
        span.set_attribute("amount", request.amount)
        span.set_attribute("payment_method", request.payment_method)
        
        logger.info(
            f"Processing payment {payment_id}",
            extra={
                "action": "process_payment",
                "payment_id": payment_id,
                "order_id": request.order_id,
                "amount": request.amount,
                "payment_method": request.payment_method
            }
        )
        
        # Step 1: Reserve inventory
        with tracer.start_as_current_span("reserve_inventory_call") as inventory_span:
            inventory_span.set_attribute("item_id", request.item_id)
            inventory_span.set_attribute("quantity", request.quantity)
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{INVENTORY_SERVICE_URL}/inventory/reserve",
                        json={
                            "item_id": request.item_id,
                            "quantity": request.quantity
                        },
                        timeout=10.0
                    )
                    
                    if response.status_code != 200:
                        logger.error(
                            f"Inventory reservation failed: {response.text}",
                            extra={
                                "action": "process_payment",
                                "payment_id": payment_id,
                                "error": "inventory_reservation_failed",
                                "status_code": response.status_code
                            }
                        )
                        return PaymentResponse(
                            success=False,
                            payment_id=payment_id,
                            order_id=request.order_id,
                            amount=request.amount,
                            status="failed",
                            trace_id=get_current_trace_id(),
                            message=f"Inventory reservation failed: {response.text}"
                        )
                        
            except httpx.RequestError as e:
                logger.error(
                    f"Failed to connect to inventory service: {e}",
                    extra={
                        "action": "process_payment",
                        "payment_id": payment_id,
                        "error": "inventory_service_unavailable"
                    }
                )
                raise HTTPException(
                    status_code=503,
                    detail="Inventory service unavailable"
                )
        
        # Step 2: Process payment (simulated)
        with tracer.start_as_current_span("payment_gateway") as gateway_span:
            gateway_span.set_attribute("payment_method", request.payment_method)
            
            # Simulate payment processing time
            await asyncio.sleep(0.1)
            
            # Simulate occasional payment failures (5% chance)
            import random
            if random.random() < 0.05:
                logger.error(
                    f"Payment gateway rejected transaction",
                    extra={
                        "action": "process_payment",
                        "payment_id": payment_id,
                        "error": "payment_gateway_rejection"
                    }
                )
                return PaymentResponse(
                    success=False,
                    payment_id=payment_id,
                    order_id=request.order_id,
                    amount=request.amount,
                    status="rejected",
                    trace_id=get_current_trace_id(),
                    message="Payment rejected by gateway"
                )
        
        # Payment successful
        logger.info(
            f"Payment {payment_id} processed successfully",
            extra={
                "action": "process_payment",
                "payment_id": payment_id,
                "order_id": request.order_id,
                "status": "completed"
            }
        )
        
        return PaymentResponse(
            success=True,
            payment_id=payment_id,
            order_id=request.order_id,
            amount=request.amount,
            status="completed",
            trace_id=get_current_trace_id(),
            message="Payment processed successfully"
        )


@app.post("/payment/refund")
async def process_refund(payment_id: str, amount: float):
    """Process a refund for a payment."""
    refund_id = f"REF-{uuid.uuid4().hex[:12].upper()}"
    
    with tracer.start_as_current_span("process_refund") as span:
        span.set_attribute("payment_id", payment_id)
        span.set_attribute("refund_id", refund_id)
        span.set_attribute("amount", amount)
        
        logger.info(
            f"Processing refund {refund_id} for payment {payment_id}",
            extra={
                "action": "process_refund",
                "refund_id": refund_id,
                "payment_id": payment_id,
                "amount": amount
            }
        )
        
        # Simulate refund processing
        await asyncio.sleep(0.05)
        
        return {
            "success": True,
            "refund_id": refund_id,
            "payment_id": payment_id,
            "amount": amount,
            "status": "refunded",
            "trace_id": get_current_trace_id()
        }


# ============================================================================
# FAILURE INJECTION ENDPOINTS
# ============================================================================

@app.post("/stress-cpu")
async def stress_cpu(request: FailureRequest):
    """Stress the CPU for testing purposes."""
    logger.warning(
        "CPU stress test initiated",
        extra={"action": "stress_cpu", "duration": request.duration, "intensity": request.intensity}
    )
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        FailureInjector.stress_cpu,
        request.duration,
        request.intensity
    )
    
    logger.info("CPU stress test completed", extra={"action": "stress_cpu"})
    
    return {
        "status": "completed",
        "type": "cpu_stress",
        "duration": request.duration,
        "intensity": request.intensity
    }


@app.post("/slow-response")
async def slow_response(request: FailureRequest):
    """Introduce artificial latency for testing."""
    logger.warning(
        "Slow response test initiated",
        extra={"action": "slow_response", "delay": request.delay}
    )
    
    await FailureInjector.slow_response(request.delay)
    
    logger.info("Slow response test completed", extra={"action": "slow_response"})
    
    return {
        "status": "completed",
        "type": "slow_response",
        "delay_seconds": request.delay
    }


@app.post("/trigger-error")
async def trigger_error(request: FailureRequest):
    """Trigger a controlled error for testing."""
    logger.error(
        f"Intentional error triggered: {request.error_type}",
        extra={"action": "trigger_error", "error_type": request.error_type}
    )
    
    try:
        FailureInjector.trigger_error(request.error_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory-leak")
async def memory_leak(request: FailureRequest):
    """Simulate a memory leak for testing."""
    logger.warning(
        "Memory leak simulation initiated",
        extra={"action": "memory_leak", "size_mb": request.size_mb}
    )
    
    total_leaked = FailureInjector.simulate_memory_leak(request.size_mb)
    
    logger.warning(
        f"Memory leak simulated - total leaked: {total_leaked}MB",
        extra={"action": "memory_leak", "total_leaked_mb": total_leaked}
    )
    
    return {
        "status": "completed",
        "type": "memory_leak",
        "allocated_mb": request.size_mb,
        "total_leaked_mb": total_leaked
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
