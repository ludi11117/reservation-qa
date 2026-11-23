from threading import Thread

import pytest
from werkzeug.serving import make_server

from app import create_app


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "bookings.sqlite3"


@pytest.fixture
def base_url(db_path):
    server = make_server("127.0.0.1", 0, create_app(db_path), threaded=True)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
