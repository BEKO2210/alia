import asyncio
import mimetypes
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tools.evolution_data import generate

try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
    PlaywrightError = RuntimeError


ROOT = Path(__file__).parents[1]


# The site CI job sets SITE_TESTS_REQUIRE_BROWSER=1 so a missing browser fails there instead of skipping.
REQUIRE_BROWSER = os.environ.get("SITE_TESTS_REQUIRE_BROWSER") == "1"


class EvolutionPageSourceTests(unittest.TestCase):
    def test_round_cards_render_public_details_and_translated_statuses(self):
        script = (ROOT / "site/evolution/evolution.js").read_text(encoding="utf-8")
        for marker in ("round.summary", "round.interventions", "round.reviews", "out_of_scope_paths",
                       "isolation_breaches", "status.passed", '"status.passed": "bestanden"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)

    def test_status_colors_are_semantic(self):
        css = (ROOT / "site/evolution/evolution.css").read_text(encoding="utf-8")
        self.assertIn(".round-status { text-transform: capitalize; color: var(--mut); }", css)
        self.assertIn(".round-status.passed { color: var(--green); }", css)
        self.assertIn(".round-status.failed, .round-status.aborted, .round-status.invalid { color: var(--red); }", css)


@unittest.skipUnless(async_playwright or REQUIRE_BROWSER, "playwright is only installed in the site CI job")
class EvolutionPageBrowserTests(unittest.TestCase):
    def test_example_failed_round_renders_as_failed(self):
        asyncio.run(self._run())

    async def _run(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "rounds.json"
            data.write_bytes(generate(ROOT / "evolution/examples"))
            async with async_playwright() as playwright:
                try:
                    browser = await playwright.chromium.launch(headless=True)
                except PlaywrightError as exc:
                    if REQUIRE_BROWSER:
                        raise
                    self.skipTest(f"Chromium cannot launch: {exc}")
                page = await browser.new_page(viewport={"width": 390, "height": 844}, locale="en-US")

                async def route_request(route, request):
                    parsed = urlsplit(request.url)
                    relative = unquote(parsed.path).removeprefix("/alia/")
                    local = data if relative == "evolution/data/rounds.json" else ROOT / "site" / relative
                    if local.is_dir():
                        local /= "index.html"
                    await route.fulfill(
                        status=200,
                        body=local.read_bytes(),
                        content_type=mimetypes.guess_type(local.name)[0] or "application/octet-stream",
                    )

                await page.route("**/*", route_request)
                await page.add_init_script("localStorage.setItem('alia-lang', 'en')")
                await page.goto("https://site.test/alia/evolution/", wait_until="networkidle")
                failed = page.locator(".round-status.failed")
                self.assertEqual(await failed.count(), 1)
                self.assertEqual((await failed.text_content()).strip(), "failed")
                await browser.close()


if __name__ == "__main__":
    unittest.main()
