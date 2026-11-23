import subprocess
import sys
from pathlib import Path


def test_inventory_load_budget(base_url):
    Path("reports").mkdir(exist_ok=True)
    subprocess.run([
        sys.executable, "-m", "locust", "-f", "locustfile.py", "--headless",
        "--host", base_url, "-u", "5", "-r", "5", "-t", "10s", "--only-summary",
        "--stop-timeout", "3", "--csv", "reports/load", "--html", "reports/load.html",
    ], check=True, timeout=60)
