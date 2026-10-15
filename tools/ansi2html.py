#!/usr/bin/env python3
"""Turn `tmux capture-pane -e` output into a standalone HTML terminal window.

Usage: tmux capture-pane -e -p -t SESSION | python3 tools/ansi2html.py "window title" > out.html

Handles SGR colors (16, 256 and truecolor, foreground and background), bold and dim.
Block glyphs are drawn as CSS boxes because font glyphs leave seams between cells and rows.
"""
import html
import re
import sys

BASE = ["#1b1e27", "#fb7185", "#6ee7a8", "#f8d477", "#5c9dff", "#a78bfa", "#5eead4", "#e8eef7",
        "#525a6b", "#fb7185", "#6ee7a8", "#f8d477", "#76b9ff", "#c4b5fd", "#99f6e4", "#ffffff"]
BLOCKS = {"█": "f", "▀": "u", "▄": "l"}
SGR = re.compile(r"(\x1b\[[0-9;:]*m)")
BLOCK_RUN = re.compile("([▀▄█]+)")

PAGE = """<!doctype html><meta charset=utf-8><style>
body{{margin:0;background:#0b0d12;padding:28px;font-family:'DejaVu Sans Mono',monospace}}
.w{{background:#10131a;border:1px solid #2a3140;border-radius:12px;box-shadow:0 20px 60px #000a;overflow:hidden;display:inline-block}}
.t{{height:34px;background:#171b24;display:flex;align-items:center;gap:8px;padding:0 14px;color:#8491a5;font-size:13px}}
.d{{width:12px;height:12px;border-radius:50%}}
pre{{margin:0;padding:16px 18px;color:#e8eef7;font-size:15px;line-height:1.17;font-family:inherit;font-variant-ligatures:none}}
.k{{display:inline-block;width:1ch;height:1.17em;vertical-align:top}}
.k.f{{background:currentColor}}.k.u{{background:linear-gradient(currentColor 50%,transparent 50%)}}
.k.l{{background:linear-gradient(transparent 50%,currentColor 50%)}}
</style><div class=w><div class=t><span class=d style=background:#fb7185></span><span class=d style=background:#f8d477></span>\
<span class=d style=background:#6ee7a8></span><span style=margin-left:10px>{title}</span></div><pre>{body}</pre></div>"""


def _channel(value: int) -> int:
    return 0 if value == 0 else 55 + value * 40


def color256(n: int) -> str:
    if n < 16:
        return BASE[n]
    if n < 232:
        n -= 16
        return f"#{_channel(n // 36):02x}{_channel((n // 6) % 6):02x}{_channel(n % 6):02x}"
    grey = 8 + (n - 232) * 10
    return f"#{grey:02x}{grey:02x}{grey:02x}"


def apply_sgr(state: dict, params: list[int]) -> None:
    i = 0
    while i < len(params):
        p = params[i]
        if p == 0:
            state.clear()
        elif p == 1:
            state["b"] = True
        elif p == 2:
            state["d"] = True
        elif p == 22:
            state.pop("b", None)
            state.pop("d", None)
        elif 30 <= p <= 37:
            state["fg"] = BASE[p - 30]
        elif 90 <= p <= 97:
            state["fg"] = BASE[p - 82]
        elif 40 <= p <= 47:
            state["bg"] = BASE[p - 40]
        elif p == 39:
            state.pop("fg", None)
        elif p == 49:
            state.pop("bg", None)
        elif p in (38, 48):
            key = "fg" if p == 38 else "bg"
            if i + 2 < len(params) and params[i + 1] == 5:
                state[key] = color256(params[i + 2])
                i += 2
            elif i + 4 < len(params) and params[i + 1] == 2:
                state[key] = "#{:02x}{:02x}{:02x}".format(*params[i + 2:i + 5])
                i += 4
        i += 1


def css(state: dict) -> str:
    parts = []
    if "fg" in state:
        parts.append("color:" + state["fg"])
    if "bg" in state:
        parts.append("background:" + state["bg"])
    if state.get("b"):
        parts.append("font-weight:700")
    if state.get("d"):
        parts.append("opacity:.6")
    return ";".join(parts)


def convert(text: str) -> str:
    out: list[str] = []
    state: dict = {}
    for part in SGR.split(text):
        if part.startswith("\x1b["):
            apply_sgr(state, [int(x) if x.isdigit() else 0 for x in re.split("[;:]", part[2:-1] or "0")])
            continue
        for piece in BLOCK_RUN.split(part):
            if not piece:
                continue
            if piece[0] in BLOCKS:
                inner = "".join(f'<i class="k {BLOCKS[ch]}"></i>' for ch in piece)
            else:
                inner = html.escape(piece)
            out.append(f'<span style="{css(state)}">{inner}</span>')
    return "".join(out)


def main() -> None:
    title = sys.argv[1] if len(sys.argv) > 1 else "alia"
    print(PAGE.format(title=html.escape(title), body=convert(sys.stdin.read())))


if __name__ == "__main__":
    main()
