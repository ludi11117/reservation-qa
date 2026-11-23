"""Explore every reachable state of two reservation keys sharing one unit."""
from collections import deque
from itertools import product

import pytest

from app import create_app


ACTIONS = tuple(product(("book", "cancel"), ("A", "B")))
INITIAL = ("missing", "missing")


def transition(state, action):
    operation, key = action
    index = ("A", "B").index(key)
    current = state[index]
    if operation == "book":
        if current != "missing":
            return 200, state  # Retry returns the original receipt, even after cancellation.
        if "active" in state:
            return 409, state
        status, following = 201, "active"
    elif current == "missing":
        return 404, state
    else:
        status, following = 200, "cancelled"

    changed = list(state)
    changed[index] = following
    return status, tuple(changed)


def reachable_states():
    """Keep the shortest public-API path to each business state."""
    paths = {INITIAL: ()}
    queue = deque([INITIAL])
    while queue:
        state = queue.popleft()
        for action in ACTIONS:
            _, following = transition(state, action)
            if following not in paths:
                paths[following] = (*paths[state], action)
                queue.append(following)
    return paths


def exercise(client, path):
    state = INITIAL
    receipts = {}
    for action in path:
        operation, key = action
        status, state = transition(state, action)
        if operation == "book":
            result = client.post("/api/reservations", json={"quantity": 1},
                                 headers={"Idempotency-Key": key})
            assert result.status_code == status, path
            if status == 201:
                location = result.headers["Location"]
                assert location not in receipts.values(), path
                receipts[key] = location
            elif status == 200:
                assert result.headers["Location"] == receipts[key], path
            else:
                assert result.json == {"error": "insufficient_stock", "available": 0}, path
        else:
            location = receipts.get(key, f"/api/reservations/missing-{key}")
            result = client.delete(location)
            assert result.status_code == status, path

        assert client.get("/api/stock").json == {"available": int("active" not in state)}, path
        for label, expected in zip(("A", "B"), state):
            check = client.get(receipts.get(label, f"/api/reservations/missing-{label}"))
            if expected == "missing":
                assert check.status_code == 404, path
            else:
                assert check.status_code == 200, path
                assert check.json == {"id": receipts[label].rsplit("/", 1)[1],
                                      "quantity": 1, "state": expected}, path


@pytest.mark.parametrize("state,path", list(reachable_states().items()),
                         ids=["-".join(s) for s in reachable_states()])
def test_all_actions_from_state(tmp_path, state, path):
    for index, action in enumerate(ACTIONS):
        client = create_app(tmp_path / f"{index}.sqlite3").test_client()
        exercise(client, (*path, action))
