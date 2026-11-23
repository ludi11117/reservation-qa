from playwright.sync_api import expect, sync_playwright


def test_review_receipt_and_release_camera(base_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(base_url)
        page.get_by_role("button", name="预约一台").click()
        expect(page.locator("#payload")).to_contain_text("HTTP 201")
        page.get_by_role("button", name="GET /api/stock 200").click()
        expect(page.locator("#payload")).to_contain_text('"available": 1')
        page.reload()
        page.get_by_role("button", name="取消预约").click()
        expect(page.locator("#stock")).to_have_text("1")
        expect(page.get_by_role("button", name="预约一台")).to_be_enabled()
        page.locator(".entry").filter(has_text="DELETE").click()
        expect(page.locator("#payload")).to_contain_text('"state": "cancelled"')
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()


def test_demo_discards_receipt_and_reuses_booking(base_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page()
        page.goto(base_url)
        page.get_by_label("模拟丢弃下一笔成功回执").check()
        page.get_by_role("button", name="预约一台").click()
        expect(page.get_by_role("status")).to_have_text("未收到预约回执，请重试")
        first = page.locator("#payload").inner_text()
        assert "HTTP 201" in first
        page.get_by_role("button", name="重试预约").click()
        expect(page.get_by_role("status")).to_have_text("预约成功")
        assert page.locator("#payload").inner_text() == first.replace("HTTP 201", "HTTP 200")
        expect(page.locator("#stock")).to_have_text("0")
        browser.close()
