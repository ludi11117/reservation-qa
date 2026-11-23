import json
import sqlite3
from pathlib import Path

import requests
from playwright.sync_api import expect, sync_playwright


def test_lost_receipt_retry(base_url, db_path):
    reports = Path("reports")
    reports.mkdir(exist_ok=True)
    receipts = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        context = browser.new_context()
        context.tracing.start(screenshots=True, snapshots=True)
        page = context.new_page()

        def lose_first_receipt(route):
            response = route.fetch(max_retries=0)
            receipts.append({
                "attempt": len(receipts) + 1,
                "key": route.request.headers.get("idempotency-key"),
                "status": response.status,
                "location": response.headers.get("location"),
                "body": response.json(),
            })
            if len(receipts) == 1:
                route.abort("connectionreset")
            else:
                route.fulfill(response=response)

        page.route("**/api/reservations", lose_first_receipt)
        try:
            page.goto(base_url)
            page.get_by_role("button", name="预约一台").click()
            expect(page.get_by_role("status")).to_have_text("未收到预约回执，请重试")
            assert requests.get(f"{base_url}/api/stock", timeout=5).json() == {"available": 0}
            page.reload()
            page.get_by_role("button", name="重试预约").click()
            expect(page.get_by_role("status")).to_have_text("预约成功")
            expect(page.locator("#stock")).to_have_text("0")
        finally:
            context.tracing.stop(path=reports / "recovery-trace.zip")
            context.close()
            browser.close()
            (reports / "recovery.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")

    original, replay = receipts
    assert [original["status"], replay["status"]] == [201, 200]
    assert original["key"] and original["key"] == replay["key"]
    assert original["location"] and original["location"] == replay["location"]
    assert original["body"] == replay["body"] == {"reserved": 1, "available": 0}
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT request_key, quantity, state FROM reservations").fetchall() == [
            (original["key"], 1, "active")
        ]
