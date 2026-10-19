"""Frozen acceptance tests for round 01: copy buttons must not cover the install commands."""
import json
import mimetypes
import os
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

SITE = Path(os.environ["SITE_ROOT"]).resolve()
VIEWPORTS = [(390, 844), (1280, 800)]
LABELS = {"en": "Copy", "de": "Kopieren"}
COMMANDS = [
    'npm install -g @qwen-code/qwen-code@0.25.1\npython3 -m pip install -U "huggingface_hub[cli]"',
    "git clone https://github.com/ggml-org/llama.cpp ~/src/llama.cpp\ncd ~/src/llama.cpp && git checkout a0e6dc7\n"
    "cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release\n"
    'cmake --build build -j"$(nproc)" --target llama-server',
    "git clone https://github.com/BEKO2210/alia\ncd alia && ./install.sh && alia doctor",
    "alia        # start agent\nalia -c     # resume session\nalia status # server PID, profile, uptime\n"
    "alia mcp    # browser & web search",
]

# Returns, per install step, the copy button geometry and whether it overlaps any code text at scroll left/right.
MEASURE = """() => {
  const hit = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  return [...document.querySelectorAll("#install ol.steps > li")].map(li => {
    const pre = li.querySelector("pre"), code = pre && pre.querySelector("code");
    const buttons = [...li.querySelectorAll("button")].filter(b => {
      const r = b.getBoundingClientRect(), s = getComputedStyle(b);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
    });
    const out = {code: code ? code.textContent : null, buttons: buttons.length, covers: []};
    if (!code || buttons.length !== 1) return out;
    const b = buttons[0], r = b.getBoundingClientRect();
    out.label = ((b.getAttribute("aria-label") || "") + " " + b.textContent).trim();
    out.size = [r.width, r.height];
    out.inside = r.left >= 0 && r.right <= innerWidth;
    const original = pre.scrollLeft;
    for (const pos of [0, Math.max(0, pre.scrollWidth - pre.clientWidth)]) {
      pre.scrollLeft = pos;
      const br = b.getBoundingClientRect(), view = pre.getBoundingClientRect();
      const walker = document.createTreeWalker(code, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const range = document.createRange();
        range.selectNodeContents(node);
        // Only the part of the text the reader can see: text scrolled out of the block is clipped, not covered.
        const shown = [...range.getClientRects()].map(t => ({left: Math.max(t.left, view.left),
          right: Math.min(t.right, view.right), top: Math.max(t.top, view.top), bottom: Math.min(t.bottom, view.bottom)}))
          .filter(t => t.left < t.right && t.top < t.bottom);
        if (shown.some(t => hit(br, t))) { out.covers.push(pos ? "right" : "left"); break; }
      }
    }
    pre.scrollLeft = original;
    return out;
  });
}"""


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


class CopyButtons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def open(self, width, height, lang):
        context = self.browser.new_context(viewport={"width": width, "height": height}, locale="en-US")
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/*", serve)
        page.add_init_script(
            f"localStorage.setItem('alia-lang', {json.dumps(lang)});"
            "window.__copied = [];"
            "Object.defineProperty(navigator, 'clipboard', {value: {writeText: async t => { window.__copied.push(t); }}});"
        )
        page.goto("https://site.test/alia/", wait_until="load")
        page.evaluate("document.fonts.ready")
        page.locator("#install").scroll_into_view_if_needed()
        return page

    def test_buttons_do_not_cover_code(self):
        for width, height in VIEWPORTS:
            for lang in LABELS:
                with self.subTest(width=width, lang=lang):
                    steps = self.open(width, height, lang).evaluate(MEASURE)
                    self.assertEqual(len(steps), 4)
                    for index, step in enumerate(steps, 1):
                        self.assertEqual(step["buttons"], 1, f"step {index}: exactly one visible button")
                        self.assertEqual(step["covers"], [], f"step {index}: copy button covers code text")

    def test_buttons_keep_label_size_and_place(self):
        for width, height in VIEWPORTS:
            for lang, label in LABELS.items():
                with self.subTest(width=width, lang=lang):
                    page = self.open(width, height, lang)
                    for index, step in enumerate(page.evaluate(MEASURE), 1):
                        self.assertEqual(step["buttons"], 1, f"step {index}: exactly one visible button")
                        self.assertIn(label, step["label"], f"step {index}: label")
                        self.assertGreaterEqual(min(step["size"]), 24, f"step {index}: tap target")
                        self.assertTrue(step["inside"], f"step {index}: button inside the viewport")
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width,
                                         "page wider than the screen")

    def test_commands_unchanged_and_copied(self):
        for width, height in VIEWPORTS:
            with self.subTest(width=width):
                page = self.open(width, height, "en")
                steps = page.evaluate(MEASURE)
                self.assertEqual([step["code"] for step in steps], COMMANDS)
                buttons = page.locator("#install ol.steps > li")
                for index in range(4):
                    buttons.nth(index).locator("button").first.click()
                self.assertEqual(page.evaluate("window.__copied"), COMMANDS)


if __name__ == "__main__":
    unittest.main()
