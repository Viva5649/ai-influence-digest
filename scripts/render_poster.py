#!/usr/bin/env python3
"""Render a weekly report Markdown into a single poster screenshot.

Self-contained: no external screenshot-generator dependency needed.
Requires: pip install jinja2 playwright && playwright install chromium

Usage:
    python3 scripts/render_poster.py \\
        --md ./output/weekly_report.md \\
        --out ./output/weekly_report.png \\
        --date "2026年04月18日"
"""

from __future__ import annotations

import argparse
import html as html_lib
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("请先安装 jinja2: pip install jinja2", file=sys.stderr)
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


DEFAULT_POSTER_WIDTH = 800
DEFAULT_AUTHOR = "作者"
DEFAULT_TEMPLATE = Path(__file__).parent / "poster_template.html"


# ---------------------------------------------------------------------------
# Markdown inline → HTML
# ---------------------------------------------------------------------------

def inline_md(text: str) -> str:
    value = html_lib.escape(text)
    value = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', value)
    value = re.sub(r'\*(.+?)\*', r'<em>\1</em>', value)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', value)
    return value


def md_to_html(text: str, skip_title: str = "") -> str:
    parts: list[str] = []
    in_code = False
    code_lines: list[str] = []
    list_items: list[str] = []
    skipped_h1 = False

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
            list_items = []

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                parts.append("<pre><code>" + html_lib.escape("\n".join(code_lines)) + "</code></pre>")
                in_code = False
                code_lines = []
            else:
                flush_list()
                in_code = True
            continue

        if in_code:
            code_lines.append(raw)
            continue

        if not stripped:
            flush_list()
            continue

        if stripped.startswith("# "):
            flush_list()
            h1_text = stripped[2:].strip()
            if not skipped_h1 and skip_title and h1_text == skip_title:
                skipped_h1 = True
                continue
            parts.append(f"<h2>{inline_md(h1_text)}</h2>")
            continue

        if stripped.startswith("## "):
            flush_list()
            parts.append(f"<h2>{inline_md(stripped[3:].strip())}</h2>")
            continue

        if stripped.startswith("### "):
            flush_list()
            parts.append(f"<h3>{inline_md(stripped[4:].strip())}</h3>")
            continue

        if stripped.startswith("- "):
            list_items.append(inline_md(stripped[2:].strip()))
            continue

        flush_list()
        parts.append(f"<p>{inline_md(stripped)}</p>")

    flush_list()
    if in_code:
        parts.append("<pre><code>" + html_lib.escape("\n".join(code_lines)) + "</code></pre>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Render HTML + screenshot
# ---------------------------------------------------------------------------

def extract_title(text: str) -> tuple[str, str]:
    """Return (title, body_without_title)."""
    for i, line in enumerate(text.splitlines()):
        if line.strip().startswith("# "):
            title = line.strip()[2:].strip()
            rest = "\n".join(text.splitlines()[i + 1:])
            return title, rest
    return Path("report").stem, text


def resolve_avatar(avatar: str, template_dir: Path) -> str:
    if not avatar:
        return ""
    if avatar.startswith(("http://", "https://", "data:", "file://")):
        return avatar
    candidate = (template_dir / avatar).resolve()
    if candidate.exists():
        return f"file://{candidate}"
    return ""


def render_html(
    template_path: Path,
    title: str,
    content_html: str,
    author_name: str,
    avatar_url: str,
    date: str,
    poster_width: int,
) -> str:
    env = Environment(loader=FileSystemLoader(str(template_path.parent)), autoescape=False)
    tmpl = env.get_template(template_path.name)
    return tmpl.render(
        title=title,
        content_html=content_html,
        author_name=author_name,
        avatar_url=resolve_avatar(avatar_url, template_path.parent),
        date=date,
        poster_width=poster_width,
    )


def take_screenshot(html_path: Path, png_path: Path) -> None:
    uri = f"file://{html_path.resolve()}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": poster_width_hint(html_path) + 80, "height": 800})
        page.goto(uri)
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        target = page.locator(".container")
        if target.count() == 0:
            target = page.locator("body")
        png_path.parent.mkdir(parents=True, exist_ok=True)
        target.first.screenshot(path=str(png_path), omit_background=True)
        browser.close()


def poster_width_hint(html_path: Path) -> int:
    try:
        text = html_path.read_text("utf-8")
        m = re.search(r'width:\s*(\d+)px', text)
        return int(m.group(1)) if m else 800
    except Exception:
        return 800


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="将周报 Markdown 渲染为单张海报截图")
    parser.add_argument("--md", required=True, help="输入 Markdown 文件路径")
    parser.add_argument("--out", default="", help="输出 PNG 路径（默认与 Markdown 同目录，同名 .png）")
    parser.add_argument("--date", default=datetime.now().strftime("%Y年%m月%d日"))
    parser.add_argument("--author-name", default=DEFAULT_AUTHOR)
    parser.add_argument("--avatar-url", default="")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--poster-width", type=int, default=DEFAULT_POSTER_WIDTH)
    parser.add_argument("--keep-html", action="store_true", help="保留中间 HTML 文件")
    args = parser.parse_args()

    md_path = Path(args.md).resolve()
    if not md_path.exists():
        print(f"Markdown 文件不存在: {md_path}", file=sys.stderr)
        sys.exit(1)

    template_path = Path(args.template).resolve()
    if not template_path.exists():
        print(f"模板文件不存在: {template_path}", file=sys.stderr)
        sys.exit(1)

    png_path = Path(args.out).resolve() if args.out else md_path.with_suffix(".png")
    html_path = png_path.with_suffix(".html")

    text = md_path.read_text("utf-8")
    title, body = extract_title(text)
    content_html = md_to_html(body, skip_title=title)

    rendered = render_html(
        template_path=template_path,
        title=title,
        content_html=content_html,
        author_name=args.author_name,
        avatar_url=args.avatar_url,
        date=args.date,
        poster_width=args.poster_width,
    )

    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(rendered, "utf-8")

    print(f"生成截图: {png_path}")
    take_screenshot(html_path, png_path)

    if not args.keep_html:
        html_path.unlink(missing_ok=True)

    print(f"完成：{png_path}")


if __name__ == "__main__":
    main()
