from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


VIEWPORTS = ((390, 844), (1280, 800))
LANGUAGES = ("en", "de")


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for value in rgb:
        channel = value / 255
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    first_luminance = relative_luminance(first)
    second_luminance = relative_luminance(second)
    return (max(first_luminance, second_luminance) + 0.05) / (min(first_luminance, second_luminance) + 0.05)


def failure(check: str, page: str, detail: str, **fields: object) -> dict[str, object]:
    return {"check": check, "page": page, **fields, "detail": detail}


def page_name(path: Path, site: Path) -> str:
    relative = path.relative_to(site).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "index" and len(parts) > 1:
        parts.pop()
    return "-".join(parts)


def parse_js_dictionary(source: str, name: str = "DE") -> dict[str, str]:
    """Parse a flat JS string map without evaluating JavaScript."""
    match = re.search(rf"\bconst\s+{re.escape(name)}\s*=\s*\{{", source)
    if not match:
        return {}
    pos = match.end()
    result: dict[str, str] = {}
    pair = re.compile(
        r'\s*("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')\s*:\s*'
        r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')\s*,?'
    )
    while pos < len(source):
        while pos < len(source) and source[pos].isspace():
            pos += 1
        if pos < len(source) and source[pos] == "}":
            return result
        item = pair.match(source, pos)
        if not item:
            raise ValueError(f"cannot parse {name} dictionary near character {pos}")
        key = _decode_js_string(item.group(1))
        value = _decode_js_string(item.group(2))
        result[key] = value
        pos = item.end()
    raise ValueError(f"unterminated {name} dictionary")


def _decode_js_string(value: str) -> str:
    quote = value[0]
    body = value[1:-1]
    if quote == '"':
        return json.loads(value)
    # JSON does not allow single-quoted strings. Decode the small JS escape subset.
    body = body.replace('\\\'', "'").replace('\\"', '"')
    return bytes(body, "utf-8").decode("unicode_escape")


def resolve_local_target(page: Path, raw_url: str, site: Path) -> tuple[Path, str | None] | None:
    raw_url = raw_url.strip()
    if not raw_url:
        return None
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() in {"http", "https", "mailto", "data", "javascript"} or parsed.netloc:
        return None
    target = page if not parsed.path else page.parent / unquote(parsed.path)
    target = target.resolve()
    try:
        target.relative_to(site.resolve())
    except ValueError:
        return target, parsed.fragment or None
    if parsed.path.endswith("/") or target.is_dir():
        target /= "index.html"
    return target, unquote(parsed.fragment) or None


def known_identity(item: dict[str, object]) -> tuple[object, ...]:
    return tuple(item.get(key) for key in ("check", "page", "viewport", "lang", "selector", "key"))


def match_known(
    failures: list[dict[str, object]], known: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    known_by_id = {known_identity(item): item for item in known}
    current_by_id = {known_identity(item): item for item in failures}
    new = [item for item in failures if known_identity(item) not in known_by_id]
    matched = [item for item in failures if known_identity(item) in known_by_id]
    fixed = [item for item in known if known_identity(item) not in current_by_id]
    return new, matched, fixed


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.title_text: list[str] = []
        self.in_title = False
        self.description = False
        self.h1_count = 0
        self.ids: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.images_missing_alt: list[str] = []
        self.buttons: list[dict[str, object]] = []
        self.i18n_text: dict[str, list[str]] = {}
        self._i18n_stack: list[tuple[str, int, list[str]]] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        void = tag in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
        if not void:
            self._depth += 1
        if tag == "html":
            self.lang = attrs.get("lang")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta" and attrs.get("name", "").lower() == "description" and attrs.get("content"):
            self.description = True
        elif tag == "h1":
            self.h1_count += 1
        if "id" in attrs and attrs["id"] is not None:
            self.ids.append(attrs["id"])
        for attr in ("href", "src", "poster"):
            if attrs.get(attr):
                self.links.append((attr, attrs[attr] or ""))
        if attrs.get("srcset"):
            for part in (attrs["srcset"] or "").split(","):
                url = part.strip().split()[0] if part.strip() else ""
                if url:
                    self.links.append(("srcset", url))
        if tag == "img" and "alt" not in attrs:
            self.images_missing_alt.append(attrs.get("src") or "<img>")
        if tag == "button":
            self.buttons.append({"depth": self._depth, "text": [], "aria": attrs.get("aria-label")})
        key = attrs.get("data-i18n")
        if key:
            self._i18n_stack.append((key, self._depth, []))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        for index in range(len(self._i18n_stack) - 1, -1, -1):
            key, depth, text = self._i18n_stack[index]
            if depth == self._depth:
                normalized = " ".join("".join(text).split())
                self.i18n_text.setdefault(key, []).append(normalized)
                self._i18n_stack.pop(index)
        if tag == "button" and self.buttons:
            for button in reversed(self.buttons):
                if button["depth"] == self._depth:
                    button["closed"] = True
                    break
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_text.append(data)
        for _, _, text in self._i18n_stack:
            text.append(data)
        for button in self.buttons:
            if not button.get("closed"):
                button["text"].append(data)  # type: ignore[union-attr]


def static_checks(site: Path) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    pages: dict[Path, SiteParser] = {}
    for path in sorted(site.rglob("*.html")):
        parser = SiteParser()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[path.resolve()] = parser
    for path, parser in pages.items():
        name = page_name(path, site.resolve())
        if not parser.lang:
            failures.append(failure("html-lang", name, "missing <html lang>"))
        if not "".join(parser.title_text).strip():
            failures.append(failure("title", name, "missing <title>"))
        if not parser.description:
            failures.append(failure("meta-description", name, "missing meta description"))
        if parser.h1_count != 1:
            failures.append(failure("h1-count", name, f"expected one h1, found {parser.h1_count}"))
        for duplicate in sorted({item for item in parser.ids if parser.ids.count(item) > 1}):
            failures.append(failure("duplicate-id", name, f"duplicate id: {duplicate}", selector=f"#{duplicate}"))
        for image in parser.images_missing_alt:
            failures.append(failure("image-alt", name, f"image has no alt: {image}", selector=image))
        for index, button in enumerate(parser.buttons, 1):
            text = "".join(button["text"]).strip()  # type: ignore[arg-type]
            if not text and not button["aria"]:
                failures.append(failure("button-name", name, "button has no text or aria-label", selector=f"button:nth-of-type({index})"))
        _check_links(site.resolve(), path, name, parser, pages, failures)
        _check_i18n(path, name, parser, failures)
    return failures


def _check_links(
    site: Path,
    path: Path,
    name: str,
    parser: SiteParser,
    pages: dict[Path, SiteParser],
    failures: list[dict[str, object]],
) -> None:
    for attr, url in parser.links:
        if attr == "href" and url.startswith("/") and not url.startswith("//"):
            failures.append(failure("absolute-root-link", name, f"absolute-root link: {url}", selector=url))
        resolved = resolve_local_target(path, url, site)
        if resolved is None:
            continue
        target, anchor = resolved
        if not target.exists():
            failures.append(failure("local-target", name, f"missing local target: {url}", selector=url))
            continue
        if anchor:
            target_parser = pages.get(target.resolve())
            if target_parser is None or anchor not in target_parser.ids:
                failures.append(failure("anchor", name, f"missing anchor: {url}", selector=url))


def _check_i18n(path: Path, name: str, parser: SiteParser, failures: list[dict[str, object]]) -> None:
    keys = set(parser.i18n_text)
    if not keys:
        return
    scripts = []
    html = path.read_text(encoding="utf-8")
    for source in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I):
        candidate = path.parent / urlsplit(source).path
        if candidate.exists():
            scripts.append(candidate.read_text(encoding="utf-8"))
    scripts.append(html)
    dictionary: dict[str, str] = {}
    for script in scripts:
        try:
            found = parse_js_dictionary(script)
        except ValueError as exc:
            failures.append(failure("i18n-parser", name, str(exc)))
            return
        if found:
            dictionary = found
            break
    de_keys = set(dictionary)
    for key in sorted(keys - de_keys):
        failures.append(failure("i18n-missing-de", name, f"missing German key: {key}", key=key))
    for key in sorted(de_keys - keys):
        failures.append(failure("i18n-unused-de", name, f"unused German key: {key}", key=key))
    for key, texts in sorted(parser.i18n_text.items()):
        distinct = {text for text in texts if text}
        if len(distinct) > 1:
            failures.append(failure("i18n-english-conflict", name, f"key has different English texts: {sorted(distinct)}", key=key))
