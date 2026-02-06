from locust import HttpUser, task, between
import random

class WebUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        """Called when a User starts."""
        self.user_id = f"user-{random.randint(1000, 9999)}"
        self.cart_items = []

    @task(3)
    def view_products(self):
        """View product list."""
        self.client.get("/products")

    @task(2)
    def add_to_cart(self):
        """Add random product to cart."""
        products = ["PROD-001", "PROD-002", "PROD-003", "PROD-004", "PROD-005"]
        item_id = random.choice(products)
        self.client.post("/cart/add", json={
            "user_id": self.user_id,
            "item_id": item_id,
            "quantity": 1
        })
        self.cart_items.append(item_id)

    @task(1)
    def view_cart(self):
        """View cart."""
        self.client.get(f"/cart/{self.user_id}")

    @task(1)
    def checkout(self):
        """Checkout if items in cart."""
        if self.cart_items:
            self.client.post("/cart/checkout", json={
                "user_id": self.user_id,
                "payment_method": "credit_card"
            })
            self.cart_items = []
