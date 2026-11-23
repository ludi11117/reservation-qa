from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import requests

from app import create_app


def test_concurrent_retries_issue_one_receipt(base_url):
    start = Barrier(8)

    def send(_):
        start.wait(timeout=5)
        return requests.post(base_url + "/api/reservations", json={"quantity": 1},
                             headers={"Idempotency-Key": "same-checkout"}, timeout=5)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(send, range(8)))
    assert sorted(r.status_code for r in responses) == [200] * 7 + [201]
    assert len({r.headers["Location"] for r in responses}) == 1
    assert all(r.json() == {"reserved": 1, "available": 0} for r in responses)


def test_cancel_rebook_and_delayed_retry(base_url):
    endpoint = base_url + "/api/reservations"
    body = {"quantity": 1}
    headers = {"Idempotency-Key": "first-booking"}
    first = requests.post(endpoint, json=body, headers=headers, timeout=5)
    assert first.status_code == 201
    url = base_url + first.headers["Location"]
    mismatch = requests.post(endpoint, json={"quantity": 2}, headers=headers, timeout=5)
    assert (mismatch.status_code, mismatch.json()) == (409, {"error": "idempotency_conflict"})
    for _ in range(2):
        cancelled = requests.delete(url, timeout=5)
        assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
        assert requests.get(base_url + "/api/stock", timeout=5).json() == {"available": 1}

    next_booking = requests.post(endpoint, json=body, timeout=5)
    assert next_booking.status_code == 201 and next_booking.headers["Location"] != first.headers["Location"]
    late = requests.post(endpoint, json=body, headers=headers, timeout=5)
    assert late.status_code == 200 and late.headers["Location"] == first.headers["Location"]
    assert requests.get(url, timeout=5).json()["state"] == "cancelled"
    assert requests.get(base_url + next_booking.headers["Location"], timeout=5).json()["state"] == "active"
    assert requests.get(base_url + "/api/stock", timeout=5).json() == {"available": 0}


def test_replay_after_app_recreation(db_path):
    headers = {"Idempotency-Key": "saved-at-checkout"}
    with create_app(db_path).test_client() as client:
        first = client.post("/api/reservations", json={"quantity": 1}, headers=headers)
        assert first.status_code == 201
    with create_app(db_path).test_client() as client:
        retry = client.post("/api/reservations", json={"quantity": 1}, headers=headers)
        assert retry.status_code == 200
        assert retry.headers["Location"] == first.headers["Location"]
        assert client.get("/api/stock").json == {"available": 0}
