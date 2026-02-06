"""
Traffic Generator for AIOps Dataset
Generates realistic traffic patterns to populate telemetry data.
"""

import time
import random
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:3000/api/cart"
PRODUCTS = ["PROD-001", "PROD-002", "PROD-003", "PROD-004", "PROD-005"]

def generate_user_id():
    return f"user-{random.randint(10000, 99999)}"

def browse_products():
    """Simulate browsing products."""
    try:
        response = requests.get(f"{BASE_URL}/products", timeout=10)
        return response.status_code == 200
    except:
        return False

def add_to_cart(user_id, product_id, quantity=1):
    """Add item to cart."""
    try:
        response = requests.post(
            f"{BASE_URL}/cart/add",
            json={"user_id": user_id, "item_id": product_id, "quantity": quantity},
            timeout=10
        )
        return response.status_code == 200
    except:
        return False

def checkout(user_id):
    """Perform checkout."""
    try:
        response = requests.post(
            f"{BASE_URL}/cart/checkout",
            json={"user_id": user_id, "payment_method": "credit_card"},
            timeout=30
        )
        return response.status_code == 200
    except:
        return False

def inject_failure(failure_type="cpu"):
    """Inject a failure for anomaly generation."""
    endpoints = {
        "cpu": ("http://localhost:8001/stress-cpu", {"duration": 2, "intensity": 0.5}),
        "latency": ("http://localhost:8001/slow-response", {"delay": 2}),
        "error": ("http://localhost:8001/trigger-error", {"error_type": "thread_pool"}),
    }
    
    if failure_type in endpoints:
        url, data = endpoints[failure_type]
        try:
            requests.post(url, json=data, timeout=30)
            return True
        except:
            return False
    return False

def simulate_user_journey():
    """Simulate a complete user journey."""
    user_id = generate_user_id()
    
    # Browse products
    browse_products()
    time.sleep(random.uniform(0.5, 1.5))
    
    # Add 1-3 items to cart
    num_items = random.randint(1, 3)
    for _ in range(num_items):
        product = random.choice(PRODUCTS)
        add_to_cart(user_id, product, random.randint(1, 2))
        time.sleep(random.uniform(0.3, 0.8))
    
    # 70% chance to checkout
    if random.random() < 0.7:
        checkout(user_id)
    
    return user_id

def run_traffic_generation(duration_minutes=5, users_per_minute=10, inject_failures=True):
    """Run traffic generation for specified duration."""
    print(f"🚀 Starting traffic generation for {duration_minutes} minutes")
    print(f"   Target: {users_per_minute} users/minute")
    print(f"   Failures: {'Enabled' if inject_failures else 'Disabled'}")
    print()
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    total_users = 0
    total_failures = 0
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        while time.time() < end_time:
            batch_start = time.time()
            
            # Submit user journeys
            futures = []
            for _ in range(users_per_minute // 6):  # Roughly per 10 seconds
                futures.append(executor.submit(simulate_user_journey))
            
            # Wait for batch
            for f in futures:
                try:
                    f.result()
                    total_users += 1
                except:
                    pass
            
            # Inject failure occasionally (10% chance per batch)
            if inject_failures and random.random() < 0.1:
                failure_type = random.choice(["cpu", "latency", "error"])
                inject_failure(failure_type)
                total_failures += 1
                print(f"  💥 Injected {failure_type} failure")
            
            # Progress update
            elapsed = time.time() - start_time
            remaining = end_time - time.time()
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Users: {total_users} | Failures: {total_failures} | Remaining: {remaining:.0f}s")
            
            # Sleep to maintain rate
            batch_duration = time.time() - batch_start
            sleep_time = max(0, 10 - batch_duration)
            time.sleep(sleep_time)
    
    print()
    print("=" * 50)
    print(f"✅ Traffic generation complete!")
    print(f"   Total users simulated: {total_users}")
    print(f"   Total failures injected: {total_failures}")
    print()
    print("📊 Now run: python extraction/extract_all.py")
    print("=" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate traffic for AIOps dataset")
    parser.add_argument("--duration", type=int, default=5, help="Duration in minutes")
    parser.add_argument("--rate", type=int, default=10, help="Users per minute")
    parser.add_argument("--no-failures", action="store_true", help="Disable failure injection")
    
    args = parser.parse_args()
    
    run_traffic_generation(
        duration_minutes=args.duration,
        users_per_minute=args.rate,
        inject_failures=not args.no_failures
    )
