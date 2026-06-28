from locust import HttpUser, between, task

# put a real JWT token here — get it from your /api/users/token endpoint
AUTH_TOKEN = "ADD_A_REAL_TOKEN_HERE"

# put a real restaurant UUID that exists in your DB
RESTAURANT_ID = "ef3e19c6-afb7-4813-9c4a-74e4351d97b9"


class CustomerUser(HttpUser):
    """
    Simulates a customer browsing the app.
    wait_time = how long each user waits between requests.
    between(1, 3) means 1-3 seconds — realistic browsing behavior.
    """

    wait_time = between(1, 3)

    @task(5)
    def view_restaurant_detail(self):
        """Most common action — weighted 5x"""
        self.client.get(
            f"/api/restaurants/{RESTAURANT_ID}",
            name="/api/restaurants/[id]",  # groups requests in UI
        )

    @task(3)
    def discover_restaurants(self):
        self.client.get(
            "/api/restaurants/?city=pune&limit=20",
            name="/api/restaurants/ (discovery)",
        )

    @task(1)
    def view_menu_categories(self):
        self.client.get(
            f"/api/restaurants/{RESTAURANT_ID}/menu-categories",
            name="/api/restaurants/[id]/menu-categories",
        )


class AuthenticatedUser(HttpUser):
    """
    Simulates an authenticated customer.
    """

    wait_time = between(2, 5)

    def on_start(self):
        """Called once when the user starts — log in first."""
        response = self.client.post(
            "/api/users/token",
            data={
                "username": "ADD_YOUR_EMAIL",
                "password": "ADD_YOUR_PASSWORD",
            },
        )
        if response.status_code == 200:
            token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {token}"}
        else:
            self.headers = {}

    @task
    def get_my_orders(self):
        self.client.get(
            "/api/orders",
            headers=self.headers,
            name="/api/orders (my orders)",
        )
