"""Frozen acceptance tests for round 03: the header of the architecture showcase page."""
import json
import mimetypes
import os
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

SITE = Path(os.environ["SITE_ROOT"]).resolve()
URL = "https://site.test/alia/showcase/architecture/"


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

    def open(self, width, height):
        context = self.browser.new_context(viewport={"width": width, "height": height}, locale="en-US")
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/*", serve)
        page.goto(URL, wait_until="load")
        page.evaluate("document.fonts.ready")
        return page


BASELINE = json.loads((Path(__file__).parent / "baseline_text.json").read_text(encoding="utf-8"))
VIEWPORTS = [(390, 844), (1280, 800)]
NAV = [["Architecture", "#architecture"], ["Request Flow", "#flow"], ["Benchmarks", "#benchmarks"],
       ["Components", "#components"]]
MEASURE = """() => {
  const header = document.querySelector("header");
  const box = e => { const r = e.getBoundingClientRect(); return {w: r.width, h: r.height, top: r.top}; };
  return {
    header: header ? box(header).h : null,
    headerText: header ? header.innerText : "",
    images: header ? [...header.querySelectorAll("img")].map(i => ({src: i.currentSrc || i.src,
      loaded: i.complete && i.naturalWidth > 0, ...box(i)})) : [],
    nav: header ? [...header.querySelectorAll("nav a")].map(a => ({text: a.innerText.trim(),
      href: a.getAttribute("href"), ...box(a)})) : [],
    h1: [...document.querySelectorAll("h1")].map(h => h.innerText.trim()),
    descriptions: [...document.querySelectorAll('meta[name="description"]')].map(m => m.getAttribute("content")),
    width: document.documentElement.scrollWidth,
    below: [...document.querySelectorAll("body > *:not(header):not(script)")].map(e => e.innerText).join("\\n"),
  };
}"""


def local_file(url):
    path = unquote(urlsplit(url).path)
    if not path.startswith("/alia/"):
        return None
    return SITE / path[len("/alia/"):]


class ShowcaseHeader(PageTest):
    def test_logo_is_the_start_page_logo(self):
        logo = (SITE / "logo-mark.svg").read_bytes()
        for width, height in VIEWPORTS:
            with self.subTest(width=width):
                images = self.open(width, height).evaluate(MEASURE)["images"]
                shown = [i for i in images if i["loaded"] and i["w"] >= 24 and i["h"] >= 24]
                self.assertTrue(shown, "a visible logo image in the header")
                matches = [i for i in shown if (f := local_file(i["src"])) and f.is_file() and f.read_bytes() == logo]
                self.assertTrue(matches, f"header image is site/logo-mark.svg: {[i['src'] for i in shown]}")

    def test_one_h1_and_a_description(self):
        measured = self.open(1280, 800).evaluate(MEASURE)
        self.assertEqual(measured["h1"], ["Alia, explained by Alia"])
        self.assertIn("Alia Architecture", measured["headerText"])
        self.assertEqual(len(measured["descriptions"]), 1, "exactly one description")
        description = measured["descriptions"][0] or ""
        self.assertTrue(50 <= len(description) <= 300, f"one or two sentences: {description!r}")
        self.assertIn("Alia", description)

    def test_navigation_targets_and_layout(self):
        for width, height in VIEWPORTS:
            with self.subTest(width=width):
                measured = self.open(width, height).evaluate(MEASURE)
                self.assertEqual([[link["text"], link["href"]] for link in measured["nav"]], NAV)
                for link in measured["nav"]:
                    self.assertGreaterEqual(link["w"], 24, f"{link['href']} width")
                    self.assertGreaterEqual(link["h"], 24, f"{link['href']} height")
                tops = [link["top"] for link in measured["nav"]]
                self.assertLessEqual(max(tops) - min(tops), 1, "navigation links in one row")
                self.assertLessEqual(measured["header"], 200 if width == 390 else 139, "header height")
                self.assertLessEqual(measured["width"], width, "page wider than the screen")

    def test_everything_below_the_header_unchanged(self):
        for width, height in VIEWPORTS:
            with self.subTest(width=width):
                self.assertEqual(self.open(width, height).evaluate(MEASURE)["below"], BASELINE[str(width)])
