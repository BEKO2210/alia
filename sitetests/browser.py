from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .core import LANGUAGES, VIEWPORTS, failure, page_name


CHECK_SCRIPT = r"""
() => {
  const issues = [];
  const visible = (el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity) > 0 && r.width > 0 && r.height > 0;
  };
  const selector = (el) => {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const cls = [...el.classList].slice(0, 2).map(x => `.${CSS.escape(x)}`).join("");
    if (cls) return `${el.tagName.toLowerCase()}${cls}`;
    const parent = el.parentElement;
    if (!parent) return el.tagName.toLowerCase();
    return `${selector(parent)} > ${el.tagName.toLowerCase()}:nth-child(${[...parent.children].indexOf(el) + 1})`;
  };
  const rgb = (value) => {
    const m = value.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  };
  const lum = (c) => {
    const f = c.slice(0, 3).map(x => { x /= 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; });
    return .2126 * f[0] + .7152 * f[1] + .0722 * f[2];
  };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const background = (el) => {
    for (let node = el; node; node = node.parentElement) {
      const s = getComputedStyle(node);
      if (s.backgroundImage !== "none") return null;
      const c = rgb(s.backgroundColor);
      if (c && c[3] === 1) return c;
    }
    return null;
  };
  for (const el of document.querySelectorAll("body *")) {
    if (!visible(el) || ![...el.childNodes].some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim())) continue;
    const s = getComputedStyle(el), fg = rgb(s.color), bg = background(el);
    if (!fg || !bg || fg[3] !== 1) continue;
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight, 10) >= 700;
    const needed = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
    const ratio = contrast(fg, bg);
    if (ratio + .005 < needed) issues.push({check: "contrast", selector: selector(el), detail: `contrast ${ratio.toFixed(2)}:1, needs ${needed}:1`});
  }
  const inlineException = (el) => {
    if (el.tagName !== "A") return false;
    const p = el.parentElement;
    if (!p || ["NAV", "MENU", "LI"].includes(p.tagName)) return false;
    const text = [...p.childNodes].filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent.trim()).join("");
    return Boolean(text);
  };
  for (const el of document.querySelectorAll("a,button,[role=button],input,summary")) {
    if (!visible(el) || inlineException(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 24 || r.height < 24) issues.push({check: "tap-target", selector: selector(el), detail: `target is ${r.width.toFixed(1)}x${r.height.toFixed(1)} CSS px`});
  }
  const intersects = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  for (const button of document.querySelectorAll("button")) {
    if (!visible(button) || !["absolute", "fixed"].includes(getComputedStyle(button).position)) continue;
    const blocks = new Set();
    for (let node = button.parentElement; node; node = node.parentElement) node.querySelectorAll(":scope > pre, :scope > code").forEach(x => blocks.add(x));
    if (button.parentElement) button.parentElement.querySelectorAll("pre,code").forEach(x => blocks.add(x));
    let covered = false;
    for (const block of blocks) {
      const originalScroll = block.scrollLeft;
      const positions = [0, Math.max(0, block.scrollWidth - block.clientWidth)];
      for (const position of positions) {
        block.scrollLeft = position;
        const br = button.getBoundingClientRect();
        const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
        let textNode, hit = false;
        while ((textNode = walker.nextNode())) {
          const range = document.createRange(); range.selectNodeContents(textNode);
          for (const rect of range.getClientRects()) if (intersects(br, rect)) { hit = true; break; }
          if (hit) break;
        }
        if (hit) {
          issues.push({check: "control-covers-text", selector: selector(button), detail: `control covers text at scroll ${position ? "right" : "left"}`});
          covered = true;
          break;
        }
      }
      block.scrollLeft = originalScroll;
      if (covered) break;
    }
  }
  if (document.documentElement.scrollWidth > innerWidth) issues.push({check: "horizontal-overflow", selector: "html", detail: `scrollWidth ${document.documentElement.scrollWidth} > ${innerWidth}`});
  return issues;
}
"""


async def check_page(browser: object, site: Path, out: Path, html: Path, width: int, height: int, lang: str,
                     data_override: Path | None) -> list[dict[str, object]]:
    name = page_name(html, site)
    relative = html.relative_to(site).as_posix()
    context = await browser.new_context(viewport={"width": width, "height": height})  # type: ignore[attr-defined]
    page = await context.new_page()
    runtime: list[dict[str, object]] = []

    def add_runtime(check: str, detail: str, selector: str = "document") -> None:
        runtime.append({"check": check, "selector": selector, "detail": detail})

    page.on("console", lambda msg: add_runtime("console-error", msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda error: add_runtime("page-error", str(error)))
    def request_failed(request: object) -> None:
        # Browsers abort media downloads on their own (preload, viewport-dependent sources); that is no defect.
        if request.resource_type == "media" and "ERR_ABORTED" in str(request.failure):  # type: ignore[attr-defined]
            return
        add_runtime("request-failed", f"{request.url}: {request.failure}")  # type: ignore[attr-defined]

    page.on("requestfailed", request_failed)

    async def route_request(route: object, request: object) -> None:
        parsed = urlsplit(request.url)  # type: ignore[attr-defined]
        if parsed.netloc != "site.test":
            add_runtime("external-request", request.url)  # type: ignore[attr-defined]
            await route.abort()  # type: ignore[attr-defined]
            return
        request_path = unquote(parsed.path)
        prefix = "/alia/"
        if not request_path.startswith(prefix):
            add_runtime("local-request", f"outside site prefix: {request_path}")
            await route.abort()  # type: ignore[attr-defined]
            return
        local = site / request_path[len(prefix):]
        if data_override and request_path.endswith("/evolution/data/rounds.json"):
            local = data_override
        if local.is_dir():
            local /= "index.html"
        try:
            local.resolve().relative_to(site.resolve())
        except ValueError:
            if not data_override or local != data_override:
                add_runtime("local-request", f"path escaped site: {request_path}")
                await route.abort()  # type: ignore[attr-defined]
                return
        if not local.is_file():
            add_runtime("local-request", f"missing: {request_path}")
            await route.fulfill(status=404, body="not found")  # type: ignore[attr-defined]
            return
        content_type = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        await route.fulfill(status=200, body=local.read_bytes(), content_type=content_type)  # type: ignore[attr-defined]

    await page.route("**/*", route_request)
    await page.add_init_script(f"localStorage.setItem('alia-lang', {json.dumps(lang)})")
    await page.goto(f"https://site.test/alia/{relative}", wait_until="networkidle")
    await page.evaluate("document.fonts.ready")
    runtime.extend(await page.evaluate(CHECK_SCRIPT))
    await page.screenshot(path=out / f"{name}-{width}-{lang}.png", full_page=True)
    await context.close()
    return [failure(issue["check"], name, issue["detail"], viewport=str(width), lang=lang,
                    selector=issue.get("selector", "document")) for issue in runtime]


async def browser_checks(site: Path, out: Path, data_override: Path | None = None) -> list[dict[str, object]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("browser checks require playwright==1.60.0") from exc

    results: list[dict[str, object]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for html in sorted(site.rglob("*.html")):
                for width, height in VIEWPORTS:
                    for lang in LANGUAGES:
                        results.extend(await check_page(browser, site, out, html, width, height, lang, data_override))
        finally:
            await browser.close()
    return results
