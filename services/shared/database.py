"""
Shared Database Layer for AIOps Telemetry Platform
Provides PostgreSQL (via SQLAlchemy) and Redis clients with OpenTelemetry instrumentation.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, DateTime, Text, ForeignKey, select, update
from sqlalchemy.exc import OperationalError

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError

from opentelemetry import trace
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor


# ============================================================================
# CONFIGURATION
# ============================================================================

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_USER = os.getenv("POSTGRES_USER", "aiops")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "aiops_secret")
POSTGRES_DB = os.getenv("POSTGRES_DB", "aiops")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


# ============================================================================
# FAILURE INJECTION STATE (for chaos engineering)
# ============================================================================

class FailureState:
    """Global state for simulating infrastructure failures."""
    db_connection_blocked: bool = False
    redis_latency_ms: int = 0
    db_failure_until: Optional[datetime] = None
    redis_latency_until: Optional[datetime] = None
    
    @classmethod
    def is_db_blocked(cls) -> bool:
        """Check if DB connections should be blocked."""
        if cls.db_failure_until and datetime.utcnow() > cls.db_failure_until:
            cls.db_connection_blocked = False
            cls.db_failure_until = None
        return cls.db_connection_blocked
    
    @classmethod
    def get_redis_latency(cls) -> int:
        """Get current Redis latency injection in ms."""
        if cls.redis_latency_until and datetime.utcnow() > cls.redis_latency_until:
            cls.redis_latency_ms = 0
            cls.redis_latency_until = None
        return cls.redis_latency_ms


# ============================================================================
# SQLALCHEMY MODELS
# ============================================================================

class Base(DeclarativeBase):
    pass


class Product(Base):
    """Product inventory table."""
    __tablename__ = "products"
    
    item_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "price": self.price,
            "quantity": self.quantity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Order(Base):
    """Orders table for completed checkouts."""
    __tablename__ = "orders"
    
    order_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "total_amount": self.total_amount,
            "payment_id": self.payment_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OrderItem(Base):
    """Order line items."""
    __tablename__ = "order_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(50), ForeignKey("orders.order_id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(String(50), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "item_id": self.item_id,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
        }


# ============================================================================
# ASYNC DATABASE CLASS
# ============================================================================

class AsyncDatabase:
    """
    Async PostgreSQL database client with SQLAlchemy.
    Includes auto-reconnection logic and OpenTelemetry instrumentation.
    """
    
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.engine = None
        self.session_factory = None
        self._connected = False
        self._tracer = trace.get_tracer(__name__)
        
        # Instrument asyncpg for OpenTelemetry
        AsyncPGInstrumentor().instrument()
    
    async def connect(self, max_retries: int = 5, retry_delay: float = 2.0):
        """Connect to the database with retry logic."""
        for attempt in range(max_retries):
            try:
                if FailureState.is_db_blocked():
                    raise OperationalError("DB connection blocked by failure injection", None, None)
                
                self.engine = create_async_engine(
                    self.database_url,
                    echo=False,
                    pool_size=5,
                    max_overflow=10,
                    pool_pre_ping=True,
                )
                
                self.session_factory = async_sessionmaker(
                    self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
                
                # Test connection
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                
                self._connected = True
                print(f"Database connected successfully to {POSTGRES_HOST}:{POSTGRES_PORT}")
                return
                
            except Exception as e:
                print(f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise
    
    async def disconnect(self):
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()
            self._connected = False
            print("Database disconnected")
    
    @asynccontextmanager
    async def session(self):
        """Get a database session with failure injection support."""
        if FailureState.is_db_blocked():
            raise OperationalError("DB connection blocked by failure injection", None, None)
        
        if not self._connected or not self.session_factory:
            await self.connect()
        
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    def is_connected(self) -> bool:
        return self._connected
    
    # ========================================================================
    # PRODUCT OPERATIONS
    # ========================================================================
    
    async def get_all_products(self) -> List[Dict[str, Any]]:
        """Get all products from the database."""
        with self._tracer.start_as_current_span("db.get_all_products"):
            async with self.session() as session:
                result = await session.execute(select(Product))
                products = result.scalars().all()
                return [p.to_dict() for p in products]
    
    async def get_product(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a single product by ID."""
        with self._tracer.start_as_current_span("db.get_product") as span:
            span.set_attribute("item_id", item_id)
            async with self.session() as session:
                result = await session.execute(
                    select(Product).where(Product.item_id == item_id)
                )
                product = result.scalar_one_or_none()
                return product.to_dict() if product else None
    
    async def reserve_product(self, item_id: str, quantity: int) -> Dict[str, Any]:
        """
        Reserve inventory for a product.
        Returns the updated product info or raises an exception.
        """
        with self._tracer.start_as_current_span("db.reserve_product") as span:
            span.set_attribute("item_id", item_id)
            span.set_attribute("quantity", quantity)
            
            async with self.session() as session:
                # Get product with row lock
                result = await session.execute(
                    select(Product).where(Product.item_id == item_id).with_for_update()
                )
                product = result.scalar_one_or_none()
                
                if not product:
                    raise ValueError(f"Product {item_id} not found")
                
                if product.quantity < quantity:
                    raise ValueError(f"Insufficient stock. Available: {product.quantity}")
                
                product.quantity -= quantity
                product.updated_at = datetime.utcnow()
                
                return {
                    "item_id": product.item_id,
                    "reserved": quantity,
                    "remaining": product.quantity,
                }
    
    async def restock_product(self, item_id: str, quantity: int) -> Dict[str, Any]:
        """Add stock to a product."""
        with self._tracer.start_as_current_span("db.restock_product") as span:
            span.set_attribute("item_id", item_id)
            span.set_attribute("quantity", quantity)
            
            async with self.session() as session:
                result = await session.execute(
                    select(Product).where(Product.item_id == item_id).with_for_update()
                )
                product = result.scalar_one_or_none()
                
                if not product:
                    raise ValueError(f"Product {item_id} not found")
                
                product.quantity += quantity
                product.updated_at = datetime.utcnow()
                
                return {
                    "item_id": product.item_id,
                    "added": quantity,
                    "new_total": product.quantity,
                }
    
    async def seed_products(self, products: List[Dict[str, Any]]):
        """Seed initial product data if database is empty."""
        with self._tracer.start_as_current_span("db.seed_products"):
            async with self.session() as session:
                # Check if products exist
                result = await session.execute(select(Product).limit(1))
                if result.scalar_one_or_none():
                    print("Products already exist, skipping seed")
                    return
                
                # Insert seed data
                for p in products:
                    product = Product(
                        item_id=p["item_id"],
                        name=p["name"],
                        price=p["price"],
                        quantity=p["quantity"],
                    )
                    session.add(product)
                
                print(f"Seeded {len(products)} products")
    
    # ========================================================================
    # ORDER OPERATIONS
    # ========================================================================
    
    async def create_order(
        self,
        order_id: str,
        user_id: str,
        items: List[Dict[str, Any]],
        total_amount: float,
        payment_id: Optional[str] = None,
        status: str = "completed"
    ) -> Dict[str, Any]:
        """Create an order with line items."""
        with self._tracer.start_as_current_span("db.create_order") as span:
            span.set_attribute("order_id", order_id)
            span.set_attribute("user_id", user_id)
            span.set_attribute("total_amount", total_amount)
            
            async with self.session() as session:
                # Create order
                order = Order(
                    order_id=order_id,
                    user_id=user_id,
                    total_amount=total_amount,
                    payment_id=payment_id,
                    status=status,
                )
                session.add(order)
                
                # Create order items
                for item in items:
                    order_item = OrderItem(
                        order_id=order_id,
                        item_id=item["item_id"],
                        item_name=item["name"],
                        quantity=item["quantity"],
                        unit_price=item["price"],
                    )
                    session.add(order_item)
                
                return order.to_dict()
    
    async def get_user_orders(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all orders for a user."""
        with self._tracer.start_as_current_span("db.get_user_orders") as span:
            span.set_attribute("user_id", user_id)
            
            async with self.session() as session:
                result = await session.execute(
                    select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
                )
                orders = result.scalars().all()
                
                orders_with_items = []
                for order in orders:
                    order_dict = order.to_dict()
                    
                    # Get items for this order
                    items_result = await session.execute(
                        select(OrderItem).where(OrderItem.order_id == order.order_id)
                    )
                    items = items_result.scalars().all()
                    order_dict["items"] = [item.to_dict() for item in items]
                    
                    orders_with_items.append(order_dict)
                
                return orders_with_items


# ============================================================================
# REDIS CLIENT
# ============================================================================

class RedisClient:
    """
    Async Redis client with connection pooling.
    Used for cart storage and caching.
    """
    
    CART_TTL = 3600  # 1 hour TTL for cart data
    
    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT):
        self.host = host
        self.port = port
        self.client: Optional[redis.Redis] = None
        self._connected = False
        self._tracer = trace.get_tracer(__name__)
        
        # Instrument Redis for OpenTelemetry
        RedisInstrumentor().instrument()
    
    async def connect(self, max_retries: int = 5, retry_delay: float = 2.0):
        """Connect to Redis with retry logic."""
        for attempt in range(max_retries):
            try:
                self.client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    health_check_interval=30,
                )
                
                # Test connection
                await self.client.ping()
                self._connected = True
                print(f"Redis connected successfully to {self.host}:{self.port}")
                return
                
            except Exception as e:
                print(f"Redis connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise
    
    async def disconnect(self):
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            self._connected = False
            print("Redis disconnected")
    
    def is_connected(self) -> bool:
        return self._connected
    
    async def _inject_latency(self):
        """Apply latency injection if configured."""
        latency_ms = FailureState.get_redis_latency()
        if latency_ms > 0:
            await asyncio.sleep(latency_ms / 1000.0)
    
    # ========================================================================
    # CART OPERATIONS
    # ========================================================================
    
    def _cart_key(self, user_id: str) -> str:
        """Generate Redis key for user cart."""
        return f"cart:{user_id}"
    
    async def get_cart(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's cart from Redis."""
        with self._tracer.start_as_current_span("redis.get_cart") as span:
            span.set_attribute("user_id", user_id)
            await self._inject_latency()
            
            if not self.client:
                await self.connect()
            
            cart_data = await self.client.get(self._cart_key(user_id))
            if cart_data:
                return json.loads(cart_data)
            return []
    
    async def set_cart(self, user_id: str, items: List[Dict[str, Any]]):
        """Save user's cart to Redis with TTL."""
        with self._tracer.start_as_current_span("redis.set_cart") as span:
            span.set_attribute("user_id", user_id)
            span.set_attribute("item_count", len(items))
            await self._inject_latency()
            
            if not self.client:
                await self.connect()
            
            await self.client.setex(
                self._cart_key(user_id),
                self.CART_TTL,
                json.dumps(items)
            )
    
    async def add_to_cart(self, user_id: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Add an item to the cart."""
        with self._tracer.start_as_current_span("redis.add_to_cart") as span:
            span.set_attribute("user_id", user_id)
            span.set_attribute("item_id", item.get("item_id"))
            await self._inject_latency()
            
            cart = await self.get_cart(user_id)
            
            # Check if item exists
            existing = next((i for i in cart if i["item_id"] == item["item_id"]), None)
            if existing:
                existing["quantity"] += item.get("quantity", 1)
            else:
                cart.append(item)
            
            await self.set_cart(user_id, cart)
            return cart
    
    async def remove_from_cart(self, user_id: str, item_id: str) -> List[Dict[str, Any]]:
        """Remove an item from the cart."""
        with self._tracer.start_as_current_span("redis.remove_from_cart") as span:
            span.set_attribute("user_id", user_id)
            span.set_attribute("item_id", item_id)
            await self._inject_latency()
            
            cart = await self.get_cart(user_id)
            cart = [item for item in cart if item["item_id"] != item_id]
            await self.set_cart(user_id, cart)
            return cart
    
    async def clear_cart(self, user_id: str):
        """Clear user's cart."""
        with self._tracer.start_as_current_span("redis.clear_cart") as span:
            span.set_attribute("user_id", user_id)
            await self._inject_latency()
            
            if not self.client:
                await self.connect()
            
            await self.client.delete(self._cart_key(user_id))
    
    # ========================================================================
    # GENERIC CACHE OPERATIONS
    # ========================================================================
    
    async def get(self, key: str) -> Optional[str]:
        """Get a value from Redis."""
        await self._inject_latency()
        if not self.client:
            await self.connect()
        return await self.client.get(key)
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None):
        """Set a value in Redis."""
        await self._inject_latency()
        if not self.client:
            await self.connect()
        if ttl:
            await self.client.setex(key, ttl, value)
        else:
            await self.client.set(key, value)
    
    async def delete(self, key: str):
        """Delete a key from Redis."""
        await self._inject_latency()
        if not self.client:
            await self.connect()
        await self.client.delete(key)


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

# Singleton instances (initialized on first use)
_db_instance: Optional[AsyncDatabase] = None
_redis_instance: Optional[RedisClient] = None


async def get_database() -> AsyncDatabase:
    """Get or create the database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = AsyncDatabase()
        await _db_instance.connect()
    return _db_instance


async def get_redis() -> RedisClient:
    """Get or create the Redis instance."""
    global _redis_instance
    if _redis_instance is None:
        _redis_instance = RedisClient()
        await _redis_instance.connect()
    return _redis_instance
