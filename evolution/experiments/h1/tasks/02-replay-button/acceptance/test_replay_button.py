"""Frozen acceptance tests for H1 task 02: the Replay button of the demo video."""
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


LABELS = {"en": "Replay", "de": "Nochmal"}
# Records seeks, reloads and play calls of every media element, without needing the video to decode.
SPY = """
window.__media = {plays: 0, seeks: [], loads: 0};
const P = HTMLMediaElement.prototype;
P.play = function () { window.__media.plays++; return Promise.resolve(); };
const load = P.load;
P.load = function () { window.__media.loads++; return load.call(this); };
const time = Object.getOwnPropertyDescriptor(P, "currentTime");
Object.defineProperty(P, "currentTime", {configurable: true, get() { return time.get.call(this); },
  set(v) { window.__media.seeks.push(v); time.set.call(this, v); }});
"""
# The visible buttons labelled like the Replay button, with their box and the demo video's box.
FIND = """label => {
  const box = e => { const r = e.getBoundingClientRect(); return {l: r.left, t: r.top, r: r.right, b: r.bottom}; };
  const shown = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden"; };
  const video = document.querySelector("video");
  const buttons = [...document.querySelectorAll("button")].filter(b => b.innerText.trim() === label);
  return {all: buttons.length, shown: buttons.filter(shown).map(box), video: video ? box(video) : null,
          width: document.documentElement.scrollWidth};
}"""


class ReplayButton(PageTest):
    def test_desktop_size_label_and_place(self):
        for lang, label in LABELS.items():
            with self.subTest(lang=lang):
                found = self.open(1280, 800, lang).evaluate(FIND, label)
                self.assertEqual(len(found["shown"]), 1, "exactly one visible Replay button")
                button, video = found["shown"][0], found["video"]
                self.assertGreaterEqual(button["r"] - button["l"], 24, "width")
                self.assertGreaterEqual(button["b"] - button["t"], 24, "height")
                self.assertTrue(video["l"] <= button["l"] and button["r"] <= video["r"]
                                and video["t"] <= button["t"] and button["b"] <= video["b"], "inside the video")
                self.assertGreater((button["l"] + button["r"]) / 2, (video["l"] + video["r"]) / 2, "right half")
                self.assertLess((button["t"] + button["b"]) / 2, (video["t"] + video["b"]) / 2, "top half")
                self.assertLessEqual(found["width"], 1280, "page wider than the screen")

    def test_click_restarts_video(self):
        page = self.open(1280, 800, "en", SPY)
        page.evaluate("window.__media.seeks = []; window.__media.loads = 0; window.__media.plays = 0")
        page.get_by_role("button", name="Replay", exact=True).click()
        media = page.evaluate("window.__media")
        self.assertTrue(0 in media["seeks"] or media["loads"] > 0, "video rewound to the start")
        self.assertGreater(media["plays"], 0, "video playing again")

    def test_hidden_on_phones(self):
        for lang, label in LABELS.items():
            with self.subTest(lang=lang):
                found = self.open(390, 844, lang).evaluate(FIND, label)
                self.assertEqual(found["all"], 1, "the button still exists")
                self.assertEqual(found["shown"], [], "hidden on phones")
                self.assertLessEqual(found["width"], 390, "page wider than the screen")
