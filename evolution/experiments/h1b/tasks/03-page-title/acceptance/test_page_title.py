"""Frozen acceptance tests for H1b task 03: page title and description follow the language."""
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


BASELINE = json.loads((Path(__file__).parent / "baseline_text.json").read_text(encoding="utf-8"))
EN_TITLE = "Alia \u2014 a local coding agent for the GPU you already own"
EN_DESCRIPTION = ("Alia detects your GPU, picks a benchmarked model profile, starts llama.cpp and opens a full coding "
                  "agent in your terminal. No API key, no cloud.")
HEAD = """() => ({title: document.title,
  descriptions: [...document.querySelectorAll('meta[name="description"]')].map(m => m.getAttribute("content"))})"""
GERMAN = ("ein", "eine", "der", "die", "das", "und", "deine", "dein", "kein", "keine", "f\u00fcr", "auf", "mit")


class PageTitle(PageTest):
    def assert_english(self, head):
        self.assertEqual(head["title"], EN_TITLE)
        self.assertEqual(head["descriptions"], [EN_DESCRIPTION])

    def assert_german(self, head):
        self.assertIn("Alia", head["title"])
        self.assertNotEqual(head["title"], EN_TITLE)
        self.assertEqual(len(head["descriptions"]), 1, "exactly one description")
        description = head["descriptions"][0] or ""
        self.assertNotEqual(description, EN_DESCRIPTION)
        for text in (head["title"], description):
            words = {word.strip(".,:;!?()\u2014-").lower() for word in text.split()}
            self.assertTrue(words & set(GERMAN), f"German text expected: {text!r}")
        self.assertGreater(len(description), 60, "a full description")

    def test_initial_language(self):
        self.assert_english(self.open(1280, 800, "en").evaluate(HEAD))
        self.assert_german(self.open(1280, 800, "de").evaluate(HEAD))

    def test_switching_back_and_forth(self):
        page = self.open(1280, 800, "en")
        page.locator("[data-lang=de]").click()
        german = page.evaluate(HEAD)
        self.assert_german(german)
        page.locator("[data-lang=en]").click()
        self.assert_english(page.evaluate(HEAD))
        page.locator("[data-lang=de]").click()
        self.assertEqual(page.evaluate(HEAD), german)

    def test_visible_text_unchanged(self):
        for lang in ("en", "de"):
            with self.subTest(lang=lang):
                self.assertEqual(self.open(1280, 800, lang).evaluate("document.body.innerText"), BASELINE[lang])
