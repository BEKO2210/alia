"""Frozen acceptance tests for H1 task 03: tap targets of the header and footer links."""
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


VIEWPORTS = [(390, 844), (1280, 800)]
# (text, target) of every link in the header and footer, in document order, as the start page has them.
LINKS = {
    "en": [["", "#top"], ["Features", "#features"], ["Benchmarks", "#benchmarks"], ["Install", "#install"],
           ["GitHub", "https://github.com/BEKO2210/alia"],
           ["Security", "https://github.com/BEKO2210/alia/security/policy"],
           ["Legal notice", "impressum/"], ["Privacy", "datenschutz/"]],
    "de": [["", "#top"], ["Funktionen", "#features"], ["Messwerte", "#benchmarks"], ["Installation", "#install"],
           ["GitHub", "https://github.com/BEKO2210/alia"],
           ["Sicherheit", "https://github.com/BEKO2210/alia/security/policy"],
           ["Impressum", "impressum/"], ["Datenschutz", "datenschutz/"]],
}
SECTIONS = ["#features", "#benchmarks", "#install"]
MEASURE = """() => {
  const shown = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden"; };
  const header = document.querySelector("header");
  return {
    links: [...document.querySelectorAll("header a, footer a")].map(a => {
      const r = a.getBoundingClientRect();
      return {text: a.innerText.trim(), href: a.getAttribute("href"), shown: shown(a), w: r.width, h: r.height,
              top: r.top};
    }),
    header: header.getBoundingClientRect().height,
    width: document.documentElement.scrollWidth,
  };
}"""


class LinkTargets(PageTest):
    def test_visible_links_are_24_px(self):
        for width, height in VIEWPORTS:
            for lang in LINKS:
                with self.subTest(width=width, lang=lang):
                    measured = self.open(width, height, lang).evaluate(MEASURE)
                    shown = [link for link in measured["links"] if link["shown"]]
                    self.assertTrue(shown)
                    for link in shown:
                        self.assertGreaterEqual(link["w"], 24, f"{link['href']} width")
                        self.assertGreaterEqual(link["h"], 24, f"{link['href']} height")

    def test_links_keep_text_target_and_row(self):
        for lang, expected in LINKS.items():
            with self.subTest(lang=lang):
                measured = self.open(1280, 800, lang).evaluate(MEASURE)
                self.assertEqual([[link["text"], link["href"]] for link in measured["links"]], expected)
                sections = [link for link in measured["links"] if link["href"] in SECTIONS]
                self.assertTrue(all(link["shown"] for link in sections), "section links visible on desktop")
                tops = [link["top"] for link in sections]
                self.assertLessEqual(max(tops) - min(tops), 1, "section links in one row")

    def test_bar_height_and_page_width(self):
        for width, height in VIEWPORTS:
            for lang in LINKS:
                with self.subTest(width=width, lang=lang):
                    measured = self.open(width, height, lang).evaluate(MEASURE)
                    self.assertAlmostEqual(measured["header"], 65, delta=0.5, msg="64 px bar plus its border")
                    self.assertLessEqual(measured["width"], width, "page wider than the screen")
