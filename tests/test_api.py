from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import requests


@pytest.mark.parametrize("body", [
    {}, {"quantity": 0}, {"quantity": -1}, {"quantity": True},
    {"quantity": "1"}, {"quantity": 1.5}, [],
])
def test_invalid_quantity_preserves_stock(base_url, body):
    response = requests.post(f"{base_url}/api/reservations", json=body, timeout=5)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_quantity"}
    assert requests.get(f"{base_url}/api/stock", timeout=5).json() == {"available": 1}


def test_shortage_preserves_stock(base_url):
    response = requests.post(f"{base_url}/api/reservations", json={"quantity": 2}, timeout=5)
    assert response.status_code == 409
    assert response.json() == {"error": "insufficient_stock", "available": 1}
    assert requests.get(f"{base_url}/api/stock", timeout=5).json() == {"available": 1}


def test_competing_for_last_unit(base_url):
    start = Barrier(8)

    def reserve():
        start.wait(timeout=5)
        return requests.post(f"{base_url}/api/reservations", json={"quantity": 1}, timeout=5)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = [job.result() for job in [pool.submit(reserve) for _ in range(8)]]
    assert sorted(r.status_code for r in responses) == [201] + [409] * 7
    assert requests.get(f"{base_url}/api/stock", timeout=5).json() == {"available": 0}
