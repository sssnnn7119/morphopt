"""Check local Markdown links, heading anchors, images and Python syntax."""

import ast
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from number_docs import slug

FENCE = re.compile(r'^```([^\n]*)\n(.*?)^```\s*$', re.M | re.S)
LINK = re.compile(r'!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)')
ANCHOR = re.compile(r'<a\s+(?:id|name)=["\']([^"\']+)["\']')


def main():
    documents = [ROOT / 'README.md', *sorted((ROOT / 'docs').rglob('*.md')),
                 *sorted((ROOT / 'examples').rglob('*.md'))]
    errors, links, snippets = [], 0, 0
    anchors = {}
    for document in documents:
        text = document.read_text(encoding='utf-8')
        for fence in FENCE.finditer(text):
            if fence[1].strip() == 'python':
                snippets += 1
                try:
                    ast.parse(fence[2])
                except SyntaxError as error:
                    line = text[:fence.start(2)].count('\n') + error.lineno
                    errors.append(f'{document.relative_to(ROOT)}:{line}: {error.msg}')
        text = FENCE.sub('', text)
        for match in LINK.finditer(text):
            target = match[1].strip('<>')
            split = urlsplit(target)
            if split.scheme or target.startswith('//'):
                continue
            links += 1
            path = (document.parent / unquote(split.path)).resolve() if split.path else document.resolve()
            if not path.exists():
                errors.append(f'{document.relative_to(ROOT)}: missing {target}')
            elif split.fragment and path.suffix == '.md':
                if path not in anchors:
                    content = FENCE.sub('', path.read_text(encoding='utf-8'))
                    ids = set(ANCHOR.findall(content))
                    counts = {}
                    for heading in re.findall(r'^#{1,6}\s+(.+)$', content, re.M):
                        key = slug(heading)
                        index = counts.get(key, 0)
                        ids.add(key + (f'-{index}' if index else ''))
                        counts[key] = index + 1
                    anchors[path] = ids
                if unquote(split.fragment) not in anchors[path]:
                    errors.append(f'{document.relative_to(ROOT)}: missing anchor {target}')
    for error in errors:
        print(error)
    print(f'{len(documents)} documents; {links} local links; {snippets} Python blocks; {len(errors)} errors')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
