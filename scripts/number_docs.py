"""Generate hierarchical section numbers and marked TOCs in docs/**/*.md.

Run from any directory: python scripts/number_docs.py [--watch]
Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import html
from pathlib import Path
import re
import time
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")
NUMBER = re.compile(r"^\d+(?:\.\d+)*\.?[ \t]+")
ANCHOR = re.compile(r'<a\s+(?:id|name)=[\"\']([^\"\']+)[\"\']\s*></a>')
TOC = re.compile(
    r"^<!-- docs:toc depth=([1-5]) -->\n.*?^<!-- /docs:toc -->",
    re.MULTILINE | re.DOTALL,
)
TOC_TITLES = {"目录", "contents", "table of contents"}
LINK = re.compile(r"(?<=\]\()([^\s)]+)(?=\s|\))")


@dataclass
class Section:
    line: int
    depth: int
    title: str
    number: str
    anchor: str
    add_anchor: bool
    group: str


def slug(title: str) -> str:
    """Match the heading slugs used by the current Markdown documents."""
    title = re.sub(r"<[^>]*>", "", title)
    title = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", title)
    title = html.unescape(title).lower().replace("\\", "")
    return re.sub(r"[^\w\- ]", "", title).replace(" ", "-")


def prose_lines(lines: list[str], *, include_toc_markers: bool = False):
    """Yield lines outside fenced code, display math, comments and TOCs."""
    fence = ""
    fence_length = 0
    in_comment = False
    in_math = False
    in_toc = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if in_toc:
            if stripped == "<!-- /docs:toc -->":
                in_toc = False
            continue
        if fence:
            if re.fullmatch(rf" {{0,3}}{re.escape(fence)}{{{fence_length},}}[ \t]*", line):
                fence = ""
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if opening:
            fence, fence_length = opening[1][0], len(opening[1])
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if not in_math and stripped.startswith("<!-- docs:toc "):
            in_toc = True
            if include_toc_markers:
                yield index, line
            continue
        if "<!--" in line:
            in_comment = "-->" not in line.split("<!--", 1)[1]
            continue
        if stripped in {"$$", r"\[", r"\]"}:
            in_math = not in_math
            continue
        if not in_math:
            yield index, line


def sections(text: str, path: Path) -> tuple[list[Section], dict[str, str]]:
    lines = text.splitlines()
    counters = [0] * 5
    ids = set(ANCHOR.findall(text))
    seen_slugs: Counter[str] = Counter()
    result = []
    redirects = {}
    group = ""
    first_title = True
    for index, line in prose_lines(lines):
        match = HEADING.match(line)
        if not match:
            continue
        level = len(match[1])
        original = re.sub(r"[ \t]+#+[ \t]*$", "", match[2])
        old_slug = slug(original)
        occurrence = seen_slugs[old_slug]
        seen_slugs[old_slug] += 1
        if occurrence:
            old_slug += f"-{occurrence}"
        if level == 1:
            if not first_title:
                group = original
            first_title = False
            continue
        title = NUMBER.sub("", original)
        if title.lower() in TOC_TITLES:
            continue
        depth = level - 1
        if any(value == 0 for value in counters[:depth - 1]):
            raise ValueError(f"{path.relative_to(ROOT)}:{index + 1}: 标题层级缺少父级")
        counters[depth - 1] += 1
        counters[depth:] = [0] * (5 - depth)
        number = ".".join(map(str, counters[:depth]))

        previous = index - 1
        while previous >= 0 and not lines[previous].strip():
            previous -= 1
        existing = ANCHOR.fullmatch(lines[previous].strip()) if previous >= 0 else None
        if existing:
            anchor = existing[1]
        else:
            base = "section-" + (slug(title) or "heading")
            anchor = base
            suffix = 1
            while anchor in ids:
                anchor = f"{base}-{suffix}"
                suffix += 1
            ids.add(anchor)
        # Explicit IDs remain authoritative; numbered heading slugs are migrated.
        if old_slug not in ids:
            redirects[old_slug] = anchor
        result.append(Section(index, depth, title, number, anchor, not existing, group))
    return result, redirects


def render(text: str, entries: list[Section]) -> str:
    by_line = {entry.line: entry for entry in entries}
    output = []
    for index, line in enumerate(text.splitlines(keepends=True)):
        entry = by_line.get(index)
        if entry is None:
            output.append(line)
            continue
        if entry.add_anchor:
            output.append(f'<a id="{entry.anchor}"></a>\n\n')
        output.append(f'{"#" * (entry.depth + 1)} {entry.number} {entry.title}\n')

    def toc(match: re.Match) -> str:
        depth = int(match[1])
        rows = []
        group = ""
        for entry in entries:
            if entry.depth > depth:
                continue
            if entry.group != group:
                group = entry.group
                if group:
                    rows.extend(["", f"**{group}**", ""])
            label = f"{entry.number} {entry.title}"
            label = label.replace("[", r"\[").replace("]", r"\]")
            rows.append(f'{"    " * (entry.depth - 1)}- [{label}](#{entry.anchor})')
        return f'<!-- docs:toc depth={depth} -->\n\n' + "\n".join(rows).strip() + "\n\n<!-- /docs:toc -->"

    rendered = "".join(output)
    starts = {
        index for index, line in prose_lines(rendered.splitlines(), include_toc_markers=True)
        if line.strip().startswith("<!-- docs:toc ")
    }
    return TOC.sub(
        lambda match: toc(match) if rendered.count("\n", 0, match.start()) in starts else match[0],
        rendered,
    )


def migrate_links(text: str, path: Path, redirects: dict[Path, dict[str, str]]) -> str:
    lines = text.splitlines(keepends=True)
    for index, line in prose_lines(text.splitlines()):
        def replace(match: re.Match) -> str:
            target = match[0]
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.fragment:
                return target
            document = (path.parent / unquote(url.path)).resolve() if url.path else path
            anchor = redirects.get(document, {}).get(unquote(url.fragment))
            return target.rsplit("#", 1)[0] + "#" + anchor if anchor else target

        ending = "\n" if lines[index].endswith("\n") else ""
        lines[index] = LINK.sub(replace, line) + ending
    return "".join(lines)


def update() -> None:
    paths = sorted((ROOT / "docs").rglob("*.md"))
    originals = {path: path.read_text(encoding="utf-8") for path in paths}
    rendered = {}
    redirects = {}
    total = 0
    for path, text in originals.items():
        entries, redirects[path] = sections(text, path)
        total += len(entries)
        rendered[path] = render(text, entries)
    # The repository README can link to sections in the generated documents.
    readme = ROOT / "README.md"
    originals[readme] = readme.read_text(encoding="utf-8")
    rendered[readme] = originals[readme]
    rendered = {path: migrate_links(text, path, redirects) for path, text in rendered.items()}
    changed = [path for path in rendered if rendered[path] != originals[path]]
    for path in changed:
        if path.read_text(encoding="utf-8") != originals[path]:
            raise ValueError(f"{path.relative_to(ROOT)}: 文件正在编辑，请重新生成")
    for path in changed:
        path.write_text(rendered[path], encoding="utf-8")
        print(f"更新 {path.relative_to(ROOT)}", flush=True)
    print(f"文档 {len(paths)} 篇，章节 {total} 个，更新 {len(changed)} 个文件。", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="监视文档编辑并自动刷新编号和目录")
    args = parser.parse_args()
    previous = None
    try:
        while True:
            paths = sorted((ROOT / "docs").rglob("*.md")) + [ROOT / "README.md"]
            snapshot = [(path, path.stat().st_mtime_ns, path.stat().st_size) for path in paths]
            if snapshot != previous:
                try:
                    update()
                except (ValueError, OSError) as error:
                    if not args.watch:
                        parser.exit(1, f"{error}\n")
                    print(error, flush=True)
                # Include our own writes so they do not trigger another refresh.
                previous = [(path, path.stat().st_mtime_ns, path.stat().st_size) for path in paths]
            if not args.watch:
                return
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
