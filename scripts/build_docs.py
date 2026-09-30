"""Build offline HTML companions. Use --check to verify without writing files."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("README.ko.md", "README.md", "docs/SPEC.md")
OUTPUTS = {name: name[:-3] + ".companion.html" for name in DOCUMENTS}
REPO = "https://github.com/yunhyok/imageMarker"
GENERATOR = "ImageMarker documentation builder 1.0"

STYLE = """
:root {color-scheme:light dark;--bg:#f8fafb;--paper:#fff;--ink:#182a35;--muted:#526773;--line:#cdd8df;--accent:#096457;--soft:#e9f2ee;--code:#edf1f4}
@media(prefers-color-scheme:dark){:root{--bg:#141d24;--paper:#1c2831;--ink:#e6edf2;--muted:#b2c1ca;--line:#41535e;--accent:#85d6be;--soft:#253c36;--code:#263640}}
*{box-sizing:border-box}html{scroll-padding-top:1.5rem}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.85 system-ui,'Malgun Gothic',sans-serif;overflow-wrap:anywhere}
a{color:var(--accent);text-underline-offset:.2em}a:hover{text-decoration-thickness:2px}button,input,select{font:inherit}a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
.skip{position:absolute;left:1rem;top:-10rem;background:var(--paper);padding:.6rem}.skip:focus{top:1rem;z-index:3}
.masthead{max-width:1320px;margin:auto;padding:2rem 2rem 1rem;display:flex;flex-wrap:wrap;justify-content:space-between;gap:.5rem;border-bottom:1px solid var(--line)}.brand{font-size:1.15rem;font-weight:700;letter-spacing:.02em}.edition{color:var(--muted)}
.layout{max-width:1320px;margin:auto;display:grid;grid-template-columns:245px minmax(0,1fr);gap:2.5rem;padding:2rem}.toc{align-self:start;position:sticky;top:1rem;max-height:calc(100vh - 2rem);overflow:auto;font-size:.9rem}.toc summary{font-weight:700;padding:.2rem 0}.toc ol{list-style:none;padding:0;margin:.7rem 0}.toc li{margin:.35rem 0}.toc a{display:block;text-decoration:none;padding:.25rem 0}.toc a:hover{text-decoration:underline}
main{min-width:0;background:var(--paper);padding:2.5rem 3rem}h1{font-size:2.35rem;line-height:1.3;letter-spacing:-.035em;margin:.2rem 0 1rem}h2{font-size:1.5rem;line-height:1.5;margin:3rem 0 1rem;border-top:1px solid var(--line);padding-top:1.5rem;letter-spacing:-.02em}h3{font-size:1.13rem;margin:1.7rem 0 .6rem}p{margin:.8rem 0 1.1rem}li{margin:.35rem 0}strong{font-weight:700}main>p:first-of-type{font-size:1.1rem;color:var(--accent)}
code,pre{font-family:Consolas,'Cascadia Code',monospace;font-size:.9em}code{background:var(--code);padding:.13rem .3rem;border-radius:3px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--code);padding:1rem 1.2rem;line-height:1.65}pre code{background:none;padding:0}img{display:block;max-width:100%;height:auto;margin:1rem auto}
.table-wrap{max-width:100%;overflow-x:auto;margin:1rem 0 1.5rem}table{border-collapse:collapse;width:100%;font-size:.92rem;line-height:1.65}th,td{padding:.75rem .7rem;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);min-width:5rem}th{background:var(--soft);font-weight:700}td:first-child{font-weight:500}table code{white-space:normal}
.overview{margin:1.5rem 0 2rem;padding:1rem 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.overview-title{font-weight:700;margin:0 0 .7rem}.flow{display:flex;flex-wrap:wrap;gap:.6rem;list-style:none;padding:0;margin:0}.flow li{flex:1 1 120px;background:var(--soft);padding:.65rem .85rem;margin:0}.flow span{display:block;color:var(--muted);font-size:.8rem}.save-route{margin:.8rem 0 0;font-size:.95rem}.footer{max-width:1320px;margin:auto;padding:1rem 2rem 2rem;color:var(--muted);font-size:.9rem}
@media(max-width:950px){.layout{grid-template-columns:1fr;gap:1rem;padding:1rem}.toc{position:static;max-height:none}.toc ol{columns:2;column-gap:1rem}.toc li{break-inside:avoid}main{padding:1.5rem}.masthead{padding:1.2rem}h1{font-size:2rem}}
@media(max-width:540px){body{font-size:15px}.layout{padding:.65rem}.toc ol{columns:1}main{padding:1.1rem}h1{font-size:1.8rem}h2{font-size:1.3rem}th,td{padding:.55rem .4rem}.flow li{flex-basis:40%}}
@media print{:root{color-scheme:light;--bg:#fff;--paper:#fff;--ink:#000;--muted:#444;--line:#bbb;--accent:#164b41;--soft:#eee;--code:#eee}.toc,.skip{display:none}.layout{display:block;padding:0}.masthead,.footer{padding:1rem 0}main{padding:0;font-size:10.5pt}h2,h3{break-after:avoid}tr,img,pre,.overview{break-inside:avoid}.table-wrap{overflow:visible}a{color:inherit;text-decoration:none}h1{font-size:24pt}}
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def target_for(source: str, url: str, image: bool = False) -> str:
    parts = urlsplit(url)
    if parts.scheme or url.startswith(("#", "//")):
        return url
    target = (ROOT / source).parent.joinpath(parts.path).resolve()
    relative = target.relative_to(ROOT).as_posix()
    if image:
        mime = mimetypes.guess_type(relative)[0]
        if mime not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError(f"Unsupported image: {relative}")
        return f"data:{mime};base64," + base64.b64encode(target.read_bytes()).decode()
    if relative in OUTPUTS.values():
        # The matching generated companion may not exist on the first build.
        return url
    if not target.exists():
        raise ValueError(f"Broken link in {source}: {url}")
    if relative in OUTPUTS:
        return parts.path[:-3] + ".companion.html" + ("#" + parts.fragment if parts.fragment else "")
    kind = "tree" if target.is_dir() else "blob"
    return f"{REPO}/{kind}/main/{quote(relative)}" + ("#" + parts.fragment if parts.fragment else "")


def overview(korean: bool) -> str:
    steps = (
        [("01", "이미지 폴더"), ("02", "라벨 세트 선택"), ("03", "Excel / CSV 연결"), ("04", "사람이 판정"), ("05", "결과 저장")]
        if korean else
        [("01", "Image folder"), ("02", "Label set"), ("03", "Excel / CSV"), ("04", "Human review"), ("05", "Save results")]
    )
    title = "한눈에 보는 작업 흐름" if korean else "Review workflow"
    route = "Excel과 CSV가 모두 필요하면: Excel 저장 → 결과 확인 → CSV 내보내기" if korean else "Need both outputs? Save Excel → verify the result → export CSV"
    items = "".join(f"<li><span>{number}</span>{label}</li>" for number, label in steps)
    return f'<section class="overview" aria-label="{title}"><p class="overview-title">{title}</p><ol class="flow">{items}</ol><p class="save-route">{route}</p></section>'


def render(source: str) -> tuple[bytes, int]:
    text = (ROOT / source).read_text(encoding="utf-8-sig")
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    tokens = md.parse(text)
    headings = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            title = tokens[index + 1].content
            anchor = f"section-{len(headings) + 1}"
            token.attrSet("id", anchor)
            headings.append((token.tag, anchor, title))
        for child in token.children or []:
            if child.type == "image":
                child.attrSet("src", target_for(source, child.attrGet("src"), image=True))
            elif child.type == "link_open":
                child.attrSet("href", target_for(source, child.attrGet("href")))
    body = md.renderer.render(tokens, md.options, {})
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    korean = source == "README.ko.md"
    lang = "ko" if korean else "en"
    toc_name = "목차" if korean else "Contents"
    skip = "본문으로 이동" if korean else "Skip to content"
    title = headings[0][2]
    toc = "".join(f'<li><a href="#{anchor}">{escape(label)}</a></li>' for level, anchor, label in headings if level == "h2")
    if source.startswith("README"):
        # Place the visual below the document heading and opening paragraphs.
        pos = body.find("<h2")
        body = body[:pos] + overview(korean) + body[pos:]
    source_url = f"{REPO}/blob/main/{source}"
    output = f'''<!doctype html>
<!-- Generated by {GENERATOR}; edit {source}, then run scripts/build_docs.py. -->
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="source" content="{source}"><meta name="source-sha256" content="{digest(text.encode())}">
<title>{escape(title)}</title><style>{STYLE}</style></head>
<body><a class="skip" href="#content">{skip}</a>
<header class="masthead"><span class="brand">ImageMarker</span><span class="edition">2.0.1 · 2026-09-30</span></header>
<div class="layout"><details class="toc" open><summary>{toc_name}</summary><nav aria-label="{toc_name}"><ol>{toc}</ol></nav></details>
<main id="content">{body}</main></div>
<footer class="footer"><a href="{source_url}">{source}</a> · <a href="{REPO}">GitHub</a> · {'브라우저에서 Ctrl+P로 인쇄' if korean else 'Print with Ctrl+P'}<br>{'본문과 이미지는 오프라인에서 열립니다. GitHub 소스 링크에는 인터넷 연결이 필요합니다.' if korean else 'Text and images work offline. GitHub source links require internet access.'}</footer></body></html>
'''
    return output.encode("utf-8"), len(headings)


class LinkCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.anchors = []
        self.local_links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        href = attrs.get("href", "")
        if href.startswith("#"):
            self.anchors.append(href[1:])
        elif href and not urlsplit(href).scheme:
            self.local_links.append(href)
        if tag == "img" and (not attrs.get("alt") or not attrs.get("src", "").startswith("data:image/")):
            raise ValueError("Images must have alt text and embedded pixels")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check freshness and links without writing")
    args = parser.parse_args()
    generated = {}
    documents = []
    for source in DOCUMENTS:
        data, headings = render(source)
        check = LinkCheck()
        check.feed(data.decode())
        if len(check.ids) != len(set(check.ids)) or set(check.anchors) - set(check.ids):
            raise ValueError(f"Invalid heading anchors in {source}")
        for link in check.local_links:
            target = (ROOT / OUTPUTS[source]).parent.joinpath(urlsplit(link).path).resolve()
            if target.relative_to(ROOT).as_posix() not in OUTPUTS.values():
                raise ValueError(f"Invalid companion link: {link}")
        generated[OUTPUTS[source]] = data
        documents.append({"source": source, "sourceSha256": digest((ROOT / source).read_text(encoding="utf-8-sig").encode()),
                          "output": OUTPUTS[source], "outputSha256": digest(data), "headingCount": headings})
    manifest = {"schemaVersion": 1, "ownershipMarker": "Owned by ImageMarker documentation builder",
                "generator": GENERATOR, "repository": "yunhyok/imageMarker", "appVersion": "2.0.1",
                "documentationDate": "2026-09-30", "sourceMarkdownCount": len(DOCUMENTS),
                "generatedHtmlCount": len(DOCUMENTS), "documents": documents}
    generated[".html-companions.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    stale = []
    for name, data in generated.items():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8").encode() != data:
                stale.append(name)
        else:
            path.write_bytes(data)
    if stale:
        print("Out of date: " + ", ".join(stale))
        return 1
    print(f"{'Checked' if args.check else 'Generated'} {len(DOCUMENTS)} HTML companions; links, anchors and embedded images valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
