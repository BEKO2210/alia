"""Frozen acceptance tests for H1b task 02: Home and End keys for the screenshot tabs."""
import json
import mimetypes
import os
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

SITE = Path(os.environ["SITE_ROOT"]).resolve()


def serve(route, request):
    parsed = urlsplit(request.url)
    path = unquote(parsed.path)
    if parsed.netloc != "site.test" or not path.startswith("/alia/"):
        route.abort()
        return
    local = SITE / path[len("/alia/"):]
    if local.is_dir():
        local /= "index.html"
    try:
        local.resolve().relative_to(SITE)
    except ValueError:
        route.abort()
        return
    if not local.is_file():
        route.fulfill(status=404, body="not found")
        return
    route.fulfill(status=200, body=local.read_bytes(),
                  content_type=mimetypes.guess_type(local.name)[0] or "application/octet-stream")


class PageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def open(self, width, height, lang, init=""):
        context = self.browser.new_context(viewport={"width": width, "height": height}, locale="en-US")
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/*", serve)
        page.add_init_script(f"localStorage.setItem('alia-lang', {json.dumps(lang)});" + init)
        page.goto("https://site.test/alia/", wait_until="load")
        page.evaluate("document.fonts.ready")
        return page


STATE = """() => [...document.querySelectorAll("[role=tab]")].map(t => ({
  id: t.id, selected: t.getAttribute("aria-selected"), focused: document.activeElement === t,
  panel: !document.getElementById(t.getAttribute("aria-controls")).hidden}))"""


class TabKeys(PageTest):
    def tabs(self, page):
        return page.locator("[role=tab]")

    def assert_selected(self, page, index):
        state = page.evaluate(STATE)
        self.assertEqual(len(state), 2)
        for i, tab in enumerate(state):
            self.assertEqual(tab["selected"], "true" if i == index else "false", f"tab {i} aria-selected")
            self.assertEqual(tab["panel"], i == index, f"panel {i} shown")
        self.assertTrue(state[index]["focused"], "selected tab has focus")

    def test_home_and_end(self):
        for lang in ("en", "de"):
            with self.subTest(lang=lang):
                page = self.open(1280, 800, lang)
                self.tabs(page).nth(0).focus()
                page.keyboard.press("End")
                self.assert_selected(page, 1)
                page.keyboard.press("End")
                self.assert_selected(page, 1)
                page.keyboard.press("Home")
                self.assert_selected(page, 0)
                page.keyboard.press("Home")
                self.assert_selected(page, 0)

    def test_arrows_and_click_still_work(self):
        page = self.open(1280, 800, "en")
        self.tabs(page).nth(0).focus()
        page.keyboard.press("ArrowRight")
        self.assert_selected(page, 1)
        page.keyboard.press("ArrowRight")
        self.assert_selected(page, 0)
        page.keyboard.press("ArrowLeft")
        self.assert_selected(page, 1)
        self.tabs(page).nth(0).click()
        self.assert_selected(page, 0)
