"""Frozen acceptance tests for H1b task 01: confirmation after copying."""
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


CLIPBOARD = ("window.__copied = [];"
             "Object.defineProperty(navigator, 'clipboard', {value: {writeText: async t => { window.__copied.push(t); }}});")
LABELS = """() => [...document.querySelectorAll("#install ol.steps > li button")].map(b => b.innerText.trim())"""
FIRST_LINES = ["npm install -g @qwen-code/qwen-code@0.25.1", "git clone https://github.com/ggml-org/llama.cpp ~/src/llama.cpp",
               "git clone https://github.com/BEKO2210/alia", "alia        # start agent"]


class CopyFeedback(PageTest):
    def buttons(self, page):
        return page.locator("#install ol.steps > li").locator("button")

    def test_confirmation_then_label(self):
        for lang, normal, done in (("en", "Copy", "Copied"), ("de", "Kopieren", "Kopiert")):
            with self.subTest(lang=lang):
                page = self.open(1280, 800, lang, CLIPBOARD)
                self.assertEqual(page.evaluate(LABELS), [normal] * 4)
                self.buttons(page).nth(1).click()
                page.wait_for_timeout(200)
                self.assertEqual(page.evaluate(LABELS), [normal, done, normal, normal])
                page.wait_for_timeout(2600)
                self.assertEqual(page.evaluate(LABELS), [normal] * 4)

    def test_language_switch_during_confirmation(self):
        page = self.open(1280, 800, "en", CLIPBOARD)
        self.buttons(page).nth(0).click()
        page.wait_for_timeout(200)
        page.locator("[data-lang=de]").click()
        page.wait_for_timeout(2600)
        self.assertEqual(page.evaluate(LABELS), ["Kopieren"] * 4)
        self.buttons(page).nth(2).click()
        page.wait_for_timeout(200)
        page.locator("[data-lang=en]").click()
        page.wait_for_timeout(2600)
        self.assertEqual(page.evaluate(LABELS), ["Copy"] * 4)

    def test_each_button_copies_its_block(self):
        page = self.open(390, 844, "en", CLIPBOARD)
        for index in range(4):
            self.buttons(page).nth(index).click()
        copied = page.evaluate("window.__copied")
        self.assertEqual(len(copied), 4)
        self.assertEqual([text.splitlines()[0] for text in copied], FIRST_LINES)
