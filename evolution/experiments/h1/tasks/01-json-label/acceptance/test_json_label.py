"""Frozen acceptance tests for H1 task 01: the German label of the Qwen3.5 9B JSON row."""
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

# The JSON row of each card, found by card title and value (not by key or class, which the fix may change).
# With mark=true both labels are replaced by placeholders and the whole page text is returned.
ROWS = """mark => {
  const row = (title, value) => {
    const card = [...document.querySelectorAll("h3")].find(h => h.innerText.trim() === title)?.parentElement;
    const dd = card && [...card.querySelectorAll("dd")].find(d => d.innerText.trim() === value);
    return dd ? dd.parentElement.querySelector("dt") : null;
  };
  const rows = [row("Qwen3.6 35B-A3B", "3/3 \u00b7 3/3"), row("Qwen3.5 9B", "\u2014")];
  const labels = rows.map(dt => dt ? dt.innerText.trim() : null);
  if (!mark) return labels;
  rows.forEach((dt, i) => { if (dt) dt.textContent = `<JSON-ROW-${i + 1}>`; });
  return document.body.innerText;
}"""


class JsonLabel(PageTest):
    def test_german_labels(self):
        labels = self.open(1280, 800, "de").evaluate(ROWS, False)
        self.assertEqual(labels[0], "JSON mit / ohne Schema")
        self.assertIsNotNone(labels[1], "Qwen3.5 9B JSON row not found")
        self.assertRegex(labels[1], r"^JSON[- ]Schema$", "German label for 'JSON schema'")

    def test_english_labels_unchanged(self):
        labels = self.open(1280, 800, "en").evaluate(ROWS, False)
        self.assertEqual(labels, ["JSON with / without schema", "JSON schema"])

    def test_all_other_text_unchanged(self):
        for lang in ("en", "de"):
            with self.subTest(lang=lang):
                self.assertEqual(self.open(1280, 800, lang).evaluate(ROWS, True), BASELINE[lang])
