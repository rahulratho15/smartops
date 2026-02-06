"""
Inventory Service - AIOps Telemetry Platform
Manages product inventory with PostgreSQL persistence and full observability instrumentation.
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
from database import AsyncDatabase, get_database


# ============================================================================
# MODELS
# ============================================================================

class InventoryItem(BaseModel):
    item_id: str
    name: str
    quantity: int
    price: float


class ReserveRequest(BaseModel):
    item_id: str
    quantity: int


class ReserveResponse(BaseModel):
    success: bool
    item_id: str
    reserved_quantity: int
    remaining_stock: int
    trace_id: str


class HealthResponse(BaseModel):
    status: str
    service: str
    pod_id: str
    version: str
    timestamp: str
    database_connected: bool = False
    

class FailureRequest(BaseModel):
    duration: Optional[float] = 5.0
    intensity: Optional[float] = 0.8
    delay: Optional[float] = 2.0
    error_type: Optional[str] = "generic"
    size_mb: Optional[int] = 10
    delay_ms: Optional[int] = 500


# ============================================================================
# SEED DATA
# ============================================================================

SEED_PRODUCTS = [
    {"item_id": "PROD-001", "name": "Laptop", "quantity": 50, "price": 999.99},
    {"item_id": "PROD-002", "name": "Smartphone", "quantity": 100, "price": 599.99},
    {"item_id": "PROD-003", "name": "Headphones", "quantity": 200, "price": 149.99},
    {"item_id": "PROD-004", "name": "Tablet", "quantity": 75, "price": 449.99},
    {"item_id": "PROD-005", "name": "Smartwatch", "quantity": 150, "price": 299.99},
]


# ============================================================================
# DATABASE INSTANCE
# ============================================================================

db: Optional[AsyncDatabase] = None


# ============================================================================
# APPLICATION SETUP
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global db
    
    logger.info("Inventory service starting", extra={"event": "startup"})
    
    # Initialize database connection
    try:
        db = await get_database()
        logger.info("Database connected successfully", extra={"event": "db_connected"})
        
        # Seed initial data
        await db.seed_products(SEED_PRODUCTS)
        logger.info("Database seeded", extra={"event": "db_seeded", "products": len(SEED_PRODUCTS)})
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", extra={"event": "db_error", "error": str(e)})
    
    yield
    
    # Cleanup
    if db:
        await db.disconnect()
    logger.info("Inventory service shutting down", extra={"event": "shutdown"})


app = FastAPI(
    title="Inventory Service",
    description="Manages product inventory for AIOps Telemetry Platform",
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
    db_connected = db.is_connected() if db else False
    
    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        service=SERVICE_NAME,
        pod_id=POD_ID,
        version=VERSION,
        timestamp=datetime.utcnow().isoformat() + 'Z',
        database_connected=db_connected
    )


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return get_metrics_response()


# ============================================================================
# BUSINESS ENDPOINTS
# ============================================================================

@app.get("/inventory")
async def list_inventory():
    """List all inventory items from PostgreSQL."""
    with tracer.start_as_current_span("list_inventory"):
        logger.info("Listing all inventory items", extra={"action": "list_inventory"})
        
        try:
            products = await db.get_all_products()
            
            # Convert to InventoryItem format for backward compatibility
            items = [
                InventoryItem(
                    item_id=p["item_id"],
                    name=p["name"],
                    quantity=p["quantity"],
                    price=p["price"]
                )
                for p in products
            ]
            
            return {"items": [item.model_dump() for item in items]}
            
        except Exception as e:
            logger.error(f"Failed to fetch inventory: {e}", extra={"action": "list_inventory", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@app.get("/inventory/{item_id}")
async def get_inventory_item(item_id: str):
    """Get a specific inventory item from PostgreSQL."""
    with tracer.start_as_current_span("get_inventory_item") as span:
        span.set_attribute("item_id", item_id)
        
        try:
            product = await db.get_product(item_id)
            
            if not product:
                logger.warning(
                    f"Item not found: {item_id}",
                    extra={"action": "get_inventory", "item_id": item_id, "found": False}
                )
                raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
            
            logger.info(
                f"Retrieved inventory item: {item_id}",
                extra={"action": "get_inventory", "item_id": item_id, "quantity": product["quantity"]}
            )
            
            return InventoryItem(
                item_id=product["item_id"],
                name=product["name"],
                quantity=product["quantity"],
                price=product["price"]
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Database error: {e}", extra={"action": "get_inventory", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@app.post("/inventory/reserve", response_model=ReserveResponse)
async def reserve_inventory(request: ReserveRequest):
    """Reserve inventory for an order using PostgreSQL transaction."""
    with tracer.start_as_current_span("reserve_inventory") as span:
        span.set_attribute("item_id", request.item_id)
        span.set_attribute("quantity", request.quantity)
        
        try:
            result = await db.reserve_product(request.item_id, request.quantity)
            
            logger.info(
                f"Reserved {request.quantity} of {request.item_id}",
                extra={
                    "action": "reserve_inventory",
                    "item_id": request.item_id,
                    "reserved": request.quantity,
                    "remaining": result["remaining"]
                }
            )
            
            return ReserveResponse(
                success=True,
                item_id=request.item_id,
                reserved_quantity=request.quantity,
                remaining_stock=result["remaining"],
                trace_id=get_current_trace_id()
            )
            
        except ValueError as e:
            # Business logic errors (not found, insufficient stock)
            error_msg = str(e)
            if "not found" in error_msg.lower():
                logger.error(
                    f"Cannot reserve - item not found: {request.item_id}",
                    extra={
                        "action": "reserve_inventory",
                        "item_id": request.item_id,
                        "error": "not_found"
                    }
                )
                raise HTTPException(status_code=404, detail=error_msg)
            else:
                logger.warning(
                    f"Insufficient stock for {request.item_id}",
                    extra={
                        "action": "reserve_inventory",
                        "item_id": request.item_id,
                        "requested": request.quantity,
                        "error": "insufficient_stock"
                    }
                )
                raise HTTPException(status_code=400, detail=error_msg)
                
        except Exception as e:
            logger.error(f"Database error during reservation: {e}", extra={"action": "reserve_inventory", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@app.post("/inventory/restock")
async def restock_inventory(item_id: str, quantity: int = Query(gt=0)):
    """Restock an inventory item in PostgreSQL."""
    with tracer.start_as_current_span("restock_inventory") as span:
        span.set_attribute("item_id", item_id)
        span.set_attribute("quantity", quantity)
        
        try:
            result = await db.restock_product(item_id, quantity)
            
            logger.info(
                f"Restocked {quantity} of {item_id}",
                extra={
                    "action": "restock_inventory",
                    "item_id": item_id,
                    "added": quantity,
                    "new_total": result["new_total"]
                }
            )
            
            return {"success": True, "item_id": item_id, "new_quantity": result["new_total"]}
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"Database error during restock: {e}", extra={"action": "restock_inventory", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


# ============================================================================
# FAILURE INJECTION ENDPOINTS
# ============================================================================

@app.post("/stress-cpu")
async def stress_cpu(request: FailureRequest):
    """
    Stress the CPU for testing purposes.
    Simulates high CPU usage scenarios.
    """
    logger.warning(
        "CPU stress test initiated",
        extra={
            "action": "stress_cpu",
            "duration": request.duration,
            "intensity": request.intensity
        }
    )
    
    # Run CPU stress in thread to not block event loop
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
    """
    Introduce artificial latency for testing.
    Simulates slow network or processing delays.
    """
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
    """
    Trigger a controlled error for testing.
    Simulates various failure scenarios.
    """
    logger.error(
        f"Intentional error triggered: {request.error_type}",
        extra={"action": "trigger_error", "error_type": request.error_type}
    )
    
    try:
        FailureInjector.trigger_error(request.error_type)
    except Exception as e:
        # Log the error and re-raise as HTTP exception
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory-leak")
async def memory_leak(request: FailureRequest):
    """
    Simulate a memory leak for testing.
    Allocates memory that is intentionally not freed.
    """
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


@app.post("/simulate-db-failure")
async def simulate_db_failure(request: FailureRequest):
    """
    Simulate a database connection failure.
    All database operations will fail for the specified duration.
    """
    logger.warning(
        "Database failure simulation initiated",
        extra={"action": "simulate_db_failure", "duration": request.duration}
    )
    
    result = FailureInjector.simulate_db_connection_loss(request.duration)
    
    logger.warning(
        f"Database failure active until: {result.get('expires_at', 'unknown')}",
        extra={"action": "simulate_db_failure", "result": result}
    )
    
    return result


@app.post("/restore-db")
async def restore_db():
    """Restore database connections after a simulated failure."""
    logger.info("Restoring database connection", extra={"action": "restore_db"})
    result = FailureInjector.restore_db_connection()
    return result


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8003"))
    uvicorn.run(app, host="0.0.0.0", port=port)
