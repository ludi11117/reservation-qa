from locust import HttpUser, between, events, task


class InventoryVisitor(HttpUser):
    wait_time = between(0.1, 0.3)

    @task(3)
    def read_stock(self):
        with self.client.get("/api/stock", catch_response=True) as response:
            if response.status_code != 200 or response.json() not in ({"available": 0}, {"available": 1}):
                response.failure("Invalid stock response")

    @task
    def reserve_then_cancel(self):
        with self.client.post("/api/reservations", json={"quantity": 1}, catch_response=True) as response:
            if response.status_code == 409 and response.json() == {"error": "insufficient_stock", "available": 0}:
                response.success()
                return
            if response.status_code != 201 or response.json() != {"reserved": 1, "available": 0}:
                response.failure("Unexpected reservation result")
                return
            location = response.headers["Location"]
        with self.client.delete(location, name="/api/reservations/:id", catch_response=True) as response:
            if response.status_code != 200 or response.json().get("state") != "cancelled":
                response.failure("Reservation was not cancelled")


@events.quitting.add_listener
def check_thresholds(environment, **kwargs):
    total = environment.stats.total
    cancellations = environment.stats.get("/api/reservations/:id", "DELETE")
    if (total.num_requests < 50 or cancellations.num_requests < 5 or total.num_failures
            or environment.runner.exceptions or total.get_response_time_percentile(0.95) > 250):
        environment.process_exit_code = 1
