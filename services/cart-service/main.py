"""
Cart Service - AIOps Telemetry Platform
Manages shopping cart with Redis caching and PostgreSQL order persistence.
Full observability instrumentation.
"""

import os
import uuid
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
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
from database import AsyncDatabase, RedisClient, get_database, get_redis


# ============================================================================
# CONFIGURATION
# ============================================================================

PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8002")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8003")


# ============================================================================
# MODELS
# ============================================================================

class CartItem(BaseModel):
    item_id: str
    name: str
    quantity: int
    price: float


class AddToCartRequest(BaseModel):
    user_id: str
    item_id: str
    quantity: int = 1


class CheckoutRequest(BaseModel):
    user_id: str
    payment_method: str = "credit_card"


class CheckoutResponse(BaseModel):
    success: bool
    order_id: str
    user_id: str
    total_amount: float
    payment_id: Optional[str] = None
    status: str
    trace_id: str
    message: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    pod_id: str
    version: str
    timestamp: str
    redis_connected: bool = False
    database_connected: bool = False


class FailureRequest(BaseModel):
    duration: Optional[float] = 5.0
    intensity: Optional[float] = 0.8
    delay: Optional[float] = 2.0
    error_type: Optional[str] = "generic"
    size_mb: Optional[int] = 10
    delay_ms: Optional[int] = 500


class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    total_amount: float
    payment_id: Optional[str]
    status: str
    created_at: str
    items: List[Dict]


# ============================================================================
# PRODUCT CATALOG (fallback if inventory service unavailable)
# ============================================================================

PRODUCTS = {
    "PROD-001": {"name": "Laptop", "price": 999.99},
    "PROD-002": {"name": "Smartphone", "price": 599.99},
    "PROD-003": {"name": "Headphones", "price": 149.99},
    "PROD-004": {"name": "Tablet", "price": 449.99},
    "PROD-005": {"name": "Smartwatch", "price": 299.99},
}


# ============================================================================
# DATABASE INSTANCES
# ============================================================================

db: Optional[AsyncDatabase] = None
redis_client: Optional[RedisClient] = None


# ============================================================================
# APPLICATION SETUP
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global db, redis_client
    
    logger.info("Cart service starting", extra={"event": "startup"})
    
    # Initialize database connections
    try:
        db = await get_database()
        logger.info("PostgreSQL connected", extra={"event": "db_connected"})
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}", extra={"event": "db_error", "error": str(e)})
    
    try:
        redis_client = await get_redis()
        logger.info("Redis connected", extra={"event": "redis_connected"})
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}", extra={"event": "redis_error", "error": str(e)})
    
    yield
    
    # Cleanup
    if db:
        await db.disconnect()
    if redis_client:
        await redis_client.disconnect()
    logger.info("Cart service shutting down", extra={"event": "shutdown"})


app = FastAPI(
    title="Cart Service",
    description="Manages shopping cart for AIOps Telemetry Platform",
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
    redis_connected = redis_client.is_connected() if redis_client else False
    db_connected = db.is_connected() if db else False
    
    status = "healthy"
    if not redis_connected or not db_connected:
        status = "degraded"
    
    return HealthResponse(
        status=status,
        service=SERVICE_NAME,
        pod_id=POD_ID,
        version=VERSION,
        timestamp=datetime.utcnow().isoformat() + 'Z',
        redis_connected=redis_connected,
        database_connected=db_connected
    )


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return get_metrics_response()


# ============================================================================
# BUSINESS ENDPOINTS
# ============================================================================

@app.get("/products")
async def list_products():
    """List all available products."""
    logger.info("Listing products", extra={"action": "list_products"})
    
    # Fetch current inventory from inventory service
    products_with_stock = []
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{INVENTORY_SERVICE_URL}/inventory",
                timeout=5.0
            )
            if response.status_code == 200:
                inventory = response.json().get("items", [])
                for item in inventory:
                    products_with_stock.append({
                        "item_id": item["item_id"],
                        "name": item["name"],
                        "price": item["price"],
                        "in_stock": item["quantity"] > 0,
                        "quantity_available": item["quantity"]
                    })
    except Exception as e:
        logger.warning(f"Could not fetch inventory: {e}", extra={"error": str(e)})
        # Fall back to static product list
        for item_id, product in PRODUCTS.items():
            products_with_stock.append({
                "item_id": item_id,
                "name": product["name"],
                "price": product["price"],
                "in_stock": True,
                "quantity_available": None
            })
    
    return {"products": products_with_stock}


@app.get("/cart/{user_id}")
async def get_cart(user_id: str):
    """Get the cart for a user from Redis."""
    with tracer.start_as_current_span("get_cart") as span:
        span.set_attribute("user_id", user_id)
        
        try:
            cart = await redis_client.get_cart(user_id)
            total = sum(item["price"] * item["quantity"] for item in cart)
            
            logger.info(
                f"Retrieved cart for user {user_id}",
                extra={
                    "action": "get_cart",
                    "user_id": user_id,
                    "item_count": len(cart),
                    "total": total
                }
            )
            
            return {
                "user_id": user_id,
                "items": cart,
                "total": total,
                "item_count": len(cart)
            }
        except Exception as e:
            logger.error(f"Redis error: {e}", extra={"action": "get_cart", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Cache error: {str(e)}")


@app.post("/cart/add")
async def add_to_cart(request: AddToCartRequest):
    """Add an item to the cart stored in Redis."""
    with tracer.start_as_current_span("add_to_cart") as span:
        span.set_attribute("user_id", request.user_id)
        span.set_attribute("item_id", request.item_id)
        span.set_attribute("quantity", request.quantity)
        
        # Get product info from inventory service or fallback
        product = None
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{INVENTORY_SERVICE_URL}/inventory/{request.item_id}",
                    timeout=5.0
                )
                if response.status_code == 200:
                    product = response.json()
        except Exception as e:
            logger.warning(f"Could not fetch product from inventory: {e}")
        
        # Fallback to local catalog
        if not product:
            if request.item_id not in PRODUCTS:
                logger.warning(
                    f"Product not found: {request.item_id}",
                    extra={
                        "action": "add_to_cart",
                        "user_id": request.user_id,
                        "item_id": request.item_id,
                        "error": "product_not_found"
                    }
                )
                raise HTTPException(status_code=404, detail="Product not found")
            product = {
                "item_id": request.item_id,
                **PRODUCTS[request.item_id]
            }
        
        # Create cart item
        cart_item = {
            "item_id": request.item_id,
            "name": product["name"],
            "quantity": request.quantity,
            "price": product["price"]
        }
        
        try:
            await redis_client.add_to_cart(request.user_id, cart_item)
            
            logger.info(
                f"Added {request.quantity} of {request.item_id} to cart for user {request.user_id}",
                extra={
                    "action": "add_to_cart",
                    "user_id": request.user_id,
                    "item_id": request.item_id,
                    "quantity": request.quantity
                }
            )
            
            return {
                "success": True,
                "message": f"Added {request.quantity} x {product['name']} to cart",
                "trace_id": get_current_trace_id()
            }
        except Exception as e:
            logger.error(f"Redis error: {e}", extra={"action": "add_to_cart", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Cache error: {str(e)}")


@app.delete("/cart/{user_id}/item/{item_id}")
async def remove_from_cart(user_id: str, item_id: str):
    """Remove an item from the cart in Redis."""
    with tracer.start_as_current_span("remove_from_cart") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("item_id", item_id)
        
        try:
            await redis_client.remove_from_cart(user_id, item_id)
            
            logger.info(
                f"Removed {item_id} from cart for user {user_id}",
                extra={
                    "action": "remove_from_cart",
                    "user_id": user_id,
                    "item_id": item_id
                }
            )
            
            return {"success": True, "message": f"Removed {item_id} from cart"}
        except Exception as e:
            logger.error(f"Redis error: {e}", extra={"action": "remove_from_cart", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Cache error: {str(e)}")


@app.delete("/cart/{user_id}")
async def clear_cart(user_id: str):
    """Clear the entire cart for a user from Redis."""
    with tracer.start_as_current_span("clear_cart") as span:
        span.set_attribute("user_id", user_id)
        
        try:
            await redis_client.clear_cart(user_id)
            
            logger.info(
                f"Cleared cart for user {user_id}",
                extra={"action": "clear_cart", "user_id": user_id}
            )
            
            return {"success": True, "message": "Cart cleared"}
        except Exception as e:
            logger.error(f"Redis error: {e}", extra={"action": "clear_cart", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Cache error: {str(e)}")


@app.post("/cart/checkout", response_model=CheckoutResponse)
async def checkout(request: CheckoutRequest):
    """
    Checkout the cart.
    This orchestrates the full checkout flow:
    1. Get cart items from Redis
    2. Calculate total
    3. Process payment (which also reserves inventory)
    4. Save order to PostgreSQL
    5. Clear cart from Redis on success
    """
    order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
    
    with tracer.start_as_current_span("checkout") as span:
        span.set_attribute("order_id", order_id)
        span.set_attribute("user_id", request.user_id)
        span.set_attribute("payment_method", request.payment_method)
        
        logger.info(
            f"Starting checkout for user {request.user_id}",
            extra={
                "action": "checkout_start",
                "order_id": order_id,
                "user_id": request.user_id
            }
        )
        
        # Step 1: Get cart from Redis
        try:
            cart = await redis_client.get_cart(request.user_id)
        except Exception as e:
            logger.error(f"Redis error during checkout: {e}", extra={"action": "checkout", "error": str(e)})
            return CheckoutResponse(
                success=False,
                order_id=order_id,
                user_id=request.user_id,
                total_amount=0,
                status="failed",
                trace_id=get_current_trace_id(),
                message=f"Cache error: {str(e)}"
            )
        
        if not cart:
            logger.warning(
                f"Checkout failed - empty cart for user {request.user_id}",
                extra={
                    "action": "checkout",
                    "order_id": order_id,
                    "error": "empty_cart"
                }
            )
            return CheckoutResponse(
                success=False,
                order_id=order_id,
                user_id=request.user_id,
                total_amount=0,
                status="failed",
                trace_id=get_current_trace_id(),
                message="Cart is empty"
            )
        
        # Step 2: Calculate total
        total_amount = sum(item["price"] * item["quantity"] for item in cart)
        span.set_attribute("total_amount", total_amount)
        span.set_attribute("item_count", len(cart))
        
        # Step 3: Process payment for each item
        with tracer.start_as_current_span("process_payments") as payment_span:
            payment_span.set_attribute("total_amount", total_amount)
            
            payment_id = None
            
            for item in cart:
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{PAYMENT_SERVICE_URL}/payment/process",
                            json={
                                "order_id": order_id,
                                "item_id": item["item_id"],
                                "quantity": item["quantity"],
                                "amount": item["price"] * item["quantity"],
                                "payment_method": request.payment_method
                            },
                            timeout=30.0
                        )
                        
                        result = response.json()
                        
                        if response.status_code != 200 or not result.get("success"):
                            logger.error(
                                f"Payment failed for item {item['item_id']}",
                                extra={
                                    "action": "checkout",
                                    "order_id": order_id,
                                    "item_id": item["item_id"],
                                    "error": "payment_failed",
                                    "response": result
                                }
                            )
                            return CheckoutResponse(
                                success=False,
                                order_id=order_id,
                                user_id=request.user_id,
                                total_amount=total_amount,
                                status="payment_failed",
                                trace_id=get_current_trace_id(),
                                message=result.get("message", "Payment failed")
                            )
                        
                        payment_id = result.get("payment_id")
                        
                except httpx.RequestError as e:
                    logger.error(
                        f"Failed to connect to payment service: {e}",
                        extra={
                            "action": "checkout",
                            "order_id": order_id,
                            "error": "payment_service_unavailable"
                        }
                    )
                    return CheckoutResponse(
                        success=False,
                        order_id=order_id,
                        user_id=request.user_id,
                        total_amount=total_amount,
                        status="service_unavailable",
                        trace_id=get_current_trace_id(),
                        message="Payment service unavailable"
                    )
        
        # Step 4: Save order to PostgreSQL
        try:
            await db.create_order(
                order_id=order_id,
                user_id=request.user_id,
                items=cart,
                total_amount=total_amount,
                payment_id=payment_id,
                status="completed"
            )
            logger.info(
                f"Order saved to database: {order_id}",
                extra={"action": "checkout", "order_id": order_id, "status": "order_saved"}
            )
        except Exception as e:
            logger.error(
                f"Failed to save order to database: {e}",
                extra={"action": "checkout", "order_id": order_id, "error": str(e)}
            )
            # Note: Payment was processed, so we log the error but still return success
            # In production, this would need proper compensation logic
        
        # Step 5: Clear cart from Redis on success
        try:
            await redis_client.clear_cart(request.user_id)
        except Exception as e:
            logger.warning(f"Failed to clear cart after checkout: {e}")
        
        logger.info(
            f"Checkout completed successfully for user {request.user_id}",
            extra={
                "action": "checkout_complete",
                "order_id": order_id,
                "user_id": request.user_id,
                "total_amount": total_amount,
                "payment_id": payment_id
            }
        )
        
        return CheckoutResponse(
            success=True,
            order_id=order_id,
            user_id=request.user_id,
            total_amount=total_amount,
            payment_id=payment_id,
            status="completed",
            trace_id=get_current_trace_id(),
            message="Checkout completed successfully"
        )


@app.get("/orders/{user_id}")
async def get_user_orders(user_id: str):
    """Get order history for a user from PostgreSQL."""
    with tracer.start_as_current_span("get_user_orders") as span:
        span.set_attribute("user_id", user_id)
        
        try:
            orders = await db.get_user_orders(user_id)
            
            logger.info(
                f"Retrieved {len(orders)} orders for user {user_id}",
                extra={"action": "get_orders", "user_id": user_id, "order_count": len(orders)}
            )
            
            return {"user_id": user_id, "orders": orders}
        except Exception as e:
            logger.error(f"Database error: {e}", extra={"action": "get_orders", "error": str(e)})
            raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


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


@app.post("/simulate-db-failure")
async def simulate_db_failure(request: FailureRequest):
    """Simulate a database connection failure."""
    logger.warning(
        "Database failure simulation initiated",
        extra={"action": "simulate_db_failure", "duration": request.duration}
    )
    
    result = FailureInjector.simulate_db_connection_loss(request.duration)
    return result


@app.post("/simulate-redis-latency")
async def simulate_redis_latency(request: FailureRequest):
    """Inject artificial latency into Redis operations."""
    logger.warning(
        "Redis latency injection initiated",
        extra={"action": "simulate_redis_latency", "delay_ms": request.delay_ms, "duration": request.duration}
    )
    
    result = FailureInjector.simulate_redis_latency(request.delay_ms, request.duration)
    return result


@app.post("/restore-db")
async def restore_db():
    """Restore database connections after a simulated failure."""
    result = FailureInjector.restore_db_connection()
    logger.info("Database connection restored", extra={"action": "restore_db"})
    return result


@app.post("/restore-redis")
async def restore_redis():
    """Remove Redis latency injection."""
    result = FailureInjector.restore_redis_latency()
    logger.info("Redis latency restored", extra={"action": "restore_redis"})
    return result


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
