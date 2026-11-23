import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def test_stale_stock_and_network_evidence(base_url):
    har = Path("reports/reservation.har")
    har.parent.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        context = browser.new_context(record_har_path=har, record_har_content="embed",
                                      record_har_url_filter=f"{base_url}/api/**")
        try:
            first, second = context.new_page(), context.new_page()
            for page in (first, second):
                page.goto(base_url)
                expect(page.locator("#stock")).to_have_text("1")
            for page, message in [(first, "预约成功"), (second, "库存不足，请下次再来")]:
                button = page.get_by_role("button", name="预约一台")
                button.click()
                expect(page.get_by_role("status")).to_have_text(message)
                expect(page.locator("#stock")).to_have_text("0")
                expect(button).to_be_disabled()
        finally:
            context.close()
            browser.close()

    entries = json.loads(har.read_text(encoding="utf-8"))["log"]["entries"]
    assert [(e["request"]["method"], urlsplit(e["request"]["url"]).path,
             e["response"]["status"]) for e in entries] == [
        ("GET", "/api/stock", 200), ("GET", "/api/stock", 200),
        ("POST", "/api/reservations", 201), ("POST", "/api/reservations", 409),
    ]
    for entry in entries[2:]:
        assert json.loads(entry["request"]["postData"]["text"]) == {"quantity": 1}
    assert json.loads(entries[2]["response"]["content"]["text"]) == {"reserved": 1, "available": 0}
    assert json.loads(entries[3]["response"]["content"]["text"]) == {"error": "insufficient_stock", "available": 0}
