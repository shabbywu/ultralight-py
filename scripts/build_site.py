"""Build the GitHub Pages documentation without importing the native library.

Install site/requirements.txt, then run this file from any working directory.
Markdown in docs/ remains the source of truth for the reference and guides.
"""

from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site"
OUTPUT = ROOT / "dist"
REPOSITORY = "https://github.com/shabbywu/ultralight-py"
CONFIG = json.loads((SOURCE / "config.json").read_text(encoding="utf-8"))
BASE_URL = CONFIG["base_url"].rstrip("/")
PAGES = (
    (
        "getting-started",
        "快速开始",
        "site/getting-started.md",
        "安装、原生窗口与离屏渲染的第一个示例。",
    ),
    ("guide", "使用指南", "docs/guide.md", "运行时、页面事件、资源加载、像素与输入。"),
    ("api", "公开 API", "docs/api.md", "Runtime、View、Session、JSValue、脚本驱动与异步桥接接口。"),
    (
        "appcore",
        "窗口与 API 注册表",
        "docs/appcore.md",
        "AppCore 原生窗口、DPI、IME、API 注册与应用循环。",
    ),
    (
        "objects",
        "对象桥接",
        "docs/objects.md",
        "Python 与 JavaScript 实时对象、共享容器和生命周期。",
    ),
    ("development", "开发指南", "docs/development.md", "源码安装、构建、性能基准和开发环境。"),
    ("architecture", "架构与维护", "docs/architecture.md", "模块职责、所有权、清理与异步桥接。"),
    ("releasing", "发布指南", "docs/releasing.md", "发行包、多平台构建与 PyPI 发布流程。"),
    ("changelog", "更新日志", "CHANGELOG.md", "版本变更与迁移记录。"),
)
EN_PAGES = (
    (
        "getting-started",
        "Getting started",
        "site/en/getting-started.md",
        "Installation, your first native window, and offscreen rendering.",
    ),
    (
        "guide",
        "User guide",
        "docs/en/guide.md",
        "Runtime lifecycle, page events, resource loading, pixels, and input.",
    ),
    (
        "api",
        "Public API",
        "docs/en/api.md",
        "Runtime, View, Session, JSValue, script driving, and async bridging interfaces.",
    ),
    (
        "appcore",
        "Windows and API registry",
        "docs/en/appcore.md",
        "AppCore windows, DPI, IME, API registration, and application loops.",
    ),
    (
        "objects",
        "Object bridging",
        "docs/en/objects.md",
        "Live Python and JavaScript objects, shared containers, and lifecycle rules.",
    ),
    (
        "development",
        "Development guide",
        "docs/en/development.md",
        "Source installation, builds, benchmarks, and development environments.",
    ),
    (
        "architecture",
        "Architecture",
        "docs/en/architecture.md",
        "Module boundaries, ownership, cleanup, and async bridging.",
    ),
    (
        "releasing",
        "Release guide",
        "docs/en/releasing.md",
        "Distributions, multi-platform builds, and PyPI publishing.",
    ),
    ("changelog", "Changelog", "docs/en/changelog.md", "Version changes and migration notes."),
)
LOCALES = {"zh-CN": PAGES, "en": EN_PAGES}
MESSAGES = {
    locale: json.loads((SOURCE / "locales" / f"{locale}.json").read_text(encoding="utf-8"))
    for locale in LOCALES
}
ROUTES = {source: f"{slug}.html" for pages in LOCALES.values() for slug, _, source, _ in pages}
ROUTES.update(
    {
        "README.md": "index.html",
        "README.zh-CN.md": "index.html",
        "docs/README.md": "index.html",
        "docs/en/README.md": "index.html",
    }
)


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def page_url(locale: str, filename: str) -> str:
    """Use one absolute production URL for each translated page."""
    path = f"{locale}/" if filename == "index.html" else f"{locale}/{filename}"
    return f"{BASE_URL}/{path}"


def write_search_metadata() -> int:
    """Publish only canonical content pages, excluding aliases and error pages."""
    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ElementTree.register_namespace("", namespace)
    sitemap = ElementTree.Element(f"{{{namespace}}}urlset")
    count = 0
    for locale, pages in LOCALES.items():
        for filename in ("index.html", *(f"{slug}.html" for slug, *_ in pages)):
            node = ElementTree.SubElement(sitemap, f"{{{namespace}}}url")
            ElementTree.SubElement(node, f"{{{namespace}}}loc").text = page_url(locale, filename)
            count += 1
    ElementTree.indent(sitemap, space="  ")
    ElementTree.ElementTree(sitemap).write(
        OUTPUT / "sitemap.xml", encoding="utf-8", xml_declaration=True
    )
    (OUTPUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8"
    )
    # Useful for branch-based publishing; Actions-based Pages still needs Settings → Pages.
    (OUTPUT / "CNAME").write_text(f"{urlsplit(BASE_URL).hostname}\n", encoding="utf-8")
    return count


def slugify(value: str, separator: str) -> str:
    """Keep Chinese headings and match the anchors used in the repository."""
    return re.sub(r"\s+", separator, re.sub(r"[^\w\-\s]", "", value.lower())).strip(separator)


def rewrite_link(url: str, source: str) -> str:
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path:
        return url
    path = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parts.path)))
    suffix = (f"?{parts.query}" if parts.query else "") + (
        f"#{parts.fragment}" if parts.fragment else ""
    )
    if path in ROUTES:
        return ROUTES[path] + suffix
    # Keep source examples, workflows, and repository files on GitHub.
    local = ROOT / path
    kind = "tree" if local.is_dir() else "blob"
    return f"{REPOSITORY}/{kind}/main/{quote(path, safe='/')}" + suffix


class SiteLinks(Treeprocessor):
    def __init__(self, md: markdown.Markdown, source: str, locale: str):
        super().__init__(md)
        self.source = source
        self.locale = locale

    def run(self, root: ElementTree.Element) -> None:
        for element in root.iter("a"):
            element.set("href", rewrite_link(element.get("href", ""), self.source))
        # Scroll wide API signatures and tables without widening the page.
        for parent in list(root.iter()):
            for index, child in enumerate(list(parent)):
                if child.tag == "table":
                    wrapper = ElementTree.Element(
                        "div",
                        {
                            "class": "table-wrap",
                            "tabindex": "0",
                            "role": "region",
                            "aria-label": MESSAGES[self.locale]["table_label"],
                        },
                    )
                    parent.remove(child)
                    wrapper.append(child)
                    parent.insert(index, wrapper)


class SiteExtension(Extension):
    def __init__(self, source: str, locale: str):
        self.source = source
        self.locale = locale
        super().__init__()

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.treeprocessors.register(SiteLinks(md, self.source, self.locale), "site_links", 1)


def render_markdown(source: str, locale: str, text: str | None = None) -> tuple[str, list[dict]]:
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc", "codehilite", SiteExtension(source, locale)],
        extension_configs={
            "toc": {
                "slugify": slugify,
                "permalink": "#",
                "permalink_title": MESSAGES[locale]["permalink"],
            },
            "codehilite": {"guess_lang": False, "css_class": "highlight"},
        },
    )
    content = md.convert(text if text is not None else (ROOT / source).read_text(encoding="utf-8"))
    return content, md.toc_tokens


def toc_links(tokens: list[dict], *, top: bool = True) -> str:
    links = []
    for token in tokens:
        if token["level"] == 1:
            links.append(toc_links(token["children"], top=top))
            continue
        links.append(f'<li><a href="#{escape(token["id"])}">{escape(token["name"])}</a>')
        if token["children"]:
            links.append(toc_links(token["children"], top=False))
        links.append("</li>")
    return f"<ul>{''.join(links)}</ul>" if any(links) else ""


def sidebar(current: str, locale: str) -> str:
    t = MESSAGES[locale]
    pages = LOCALES[locale]
    groups = (
        (t["sidebar_start"], pages[:2]),
        (t["sidebar_api"], pages[2:5]),
        (t["sidebar_development"], pages[5:]),
    )
    output = [f'<a class="sidebar-home" href="./">{escape(t["sidebar_home"])}</a>']
    for label, pages in groups:
        output.append(f'<p class="sidebar-label">{label}</p>')
        for slug, title, _, _ in pages:
            active = ' aria-current="page"' if slug == current else ""
            output.append(f'<a href="{slug}.html"{active}>{title}</a>')
    output.append(
        f'<a class="sidebar-showcase" href="https://shabbywu.github.io/ultralight-py-showcase/{locale}/">{escape(t["sidebar_showcase"])}</a>'
    )
    return "".join(output)


class SearchSections(HTMLParser):
    """Extract rendered headings and prose, including code in signatures."""

    def __init__(self, page: str, title: str):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.title = title
        self.sections: list[dict] = []
        self.heading: list[str] | None = None
        self.current = {"title": title, "page": title, "url": page, "text": ""}
        self.skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in ("h1", "h2", "h3"):
            self.flush()
            self.current["url"] = f"{self.page}#{attributes['id']}"
            self.heading = []
        if tag == "a" and attributes.get("class") == "headerlink":
            self.skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3") and self.heading is not None:
            self.current["title"] = "".join(self.heading).strip()
            self.heading = None
        if tag == "a":
            self.skip = False
        if tag in ("p", "td", "tr", "li", "pre", "h1", "h2", "h3"):
            self.current["text"] += " "

    def handle_data(self, data: str) -> None:
        if not self.skip:
            if self.heading is not None:
                self.heading.append(data)
            self.current["text"] += data

    def flush(self) -> None:
        if self.current["text"].strip():
            self.current["text"] = re.sub(r"\s+", " ", self.current["text"]).strip()
            self.sections.append(self.current)
        self.current = {"title": self.title, "page": self.title, "url": self.page, "text": ""}


class PageLinks(HTMLParser):
    """Collect local targets so broken documentation fails the Pages build."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        ident = attributes.get("id")
        if ident:
            if ident in self.ids:
                raise ValueError(f"Duplicate HTML id: {ident}")
            self.ids.add(ident)
        for attribute in ("href", "src"):
            if value := attributes.get(attribute):
                self.links.append(value)


def validate_build(indexes: dict[str, list[dict]]) -> int:
    pages = {}
    for directory, index in indexes.items():
        for filename in ["index.html", "404.html", *(f"{slug}.html" for slug, *_ in PAGES)]:
            path = (OUTPUT / directory / filename).resolve()
            parser = PageLinks()
            parser.feed(path.read_text(encoding="utf-8"))
            pages[path] = parser
        pages[(OUTPUT / directory / "index.html").resolve()].links.extend(
            entry["url"] for entry in index
        )
    sitemap = ElementTree.parse(OUTPUT / "sitemap.xml")
    pages[(OUTPUT / "index.html").resolve()].links.extend(
        node.text for node in sitemap.findall("{*}url/{*}loc") if node.text
    )
    origin = urlsplit(BASE_URL)
    count = 0
    for path, parser in pages.items():
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                if (url.scheme, url.netloc) != (origin.scheme, origin.netloc):
                    continue
                target = (OUTPUT / unquote(url.path).lstrip("/")).resolve()
            else:
                target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if target.is_dir():
                target /= "index.html"
            if not target.is_relative_to(OUTPUT.resolve()) or not target.is_file():
                raise ValueError(f"{path.name}: missing local link {link!r}")
            if url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                raise ValueError(f"{path.name}: missing section {link!r}")
            count += 1
    return count


def json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def flatten_headings(tokens: list[dict]) -> list[dict]:
    return [item for token in tokens for item in (token, *flatten_headings(token["children"]))]


def language_nav(locale: str, prefix: str, filename: str) -> str:
    links = []
    for code, label in (("zh-CN", "中文"), ("en", "EN")):
        current = ' aria-current="page"' if code == locale else ""
        links.append(
            f'<a href="{prefix}{code}/{filename}" lang="{code}" hreflang="{code}" data-language="{code}"{current}>{label}</a>'
        )
    return "".join(links)


def write_page(
    filename: str,
    title: str,
    description: str,
    content: str,
    locale: str,
    *,
    directory: str,
    current: str = "",
    fragments: dict[str, str] | None = None,
) -> None:
    prefix = "../" if directory else ""
    values = {
        **{key.upper(): escape(value) for key, value in MESSAGES[locale].items()},
        "TITLE": escape(title),
        "DESCRIPTION": escape(description),
        "CONTENT": content,
        "LANG": locale,
        "PREFIX": prefix,
        "CANONICAL_URL": escape(page_url(locale, filename)),
        "ZH_URL": escape(page_url("zh-CN", filename)),
        "EN_URL": escape(page_url("en", filename)),
        "DEFAULT_URL": escape(page_url("zh-CN", filename)),
        "ROBOTS": "noindex, follow" if filename == "404.html" else "index, follow",
        "LOCALE_NAV": language_nav(locale, prefix, filename),
        "SITE_DATA": json_script({"messages": MESSAGES[locale], "fragments": fragments or {}}),
        "API_CURRENT": ' aria-current="page"' if current in ("api", "appcore", "objects") else "",
        "GUIDE_CURRENT": ' aria-current="page"' if current in ("guide", "getting-started") else "",
    }
    layout = (SOURCE / "layout.html").read_text(encoding="utf-8")
    rendered = re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: values[match[1]], layout)
    target = OUTPUT / directory / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")


def build() -> None:
    origin = urlsplit(BASE_URL)
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.port
        or origin.path
        or origin.query
        or origin.fragment
    ):
        raise ValueError("site/config.json base_url must be an HTTPS origin without a path")
    if set(MESSAGES["zh-CN"]) != set(MESSAGES["en"]):
        raise ValueError("Both locale catalogs must contain exactly the same UI keys")
    if [page[0] for page in PAGES] != [page[0] for page in EN_PAGES]:
        raise ValueError("Chinese and English page lists must match")
    OUTPUT.mkdir(exist_ok=True)
    shutil.copytree(SOURCE / "assets", OUTPUT / "assets", dirs_exist_ok=True)
    (OUTPUT / "assets/highlight.css").write_text(
        HtmlFormatter(style="native").get_style_defs(".highlight"), encoding="utf-8"
    )
    documents = {
        (locale, slug): render_markdown(source, locale)
        for locale, pages in LOCALES.items()
        for slug, _, source, _ in pages
    }
    # Pair sections in source order so language switches preserve their location.
    fragment_maps = {}
    for slug, *_ in PAGES:
        zh = flatten_headings(documents["zh-CN", slug][1])
        en = flatten_headings(documents["en", slug][1])
        if [heading["level"] for heading in zh] != [heading["level"] for heading in en]:
            raise ValueError(f"{slug}: translated section structure differs from Chinese")
        fragment_maps["zh-CN", slug] = {a["id"]: b["id"] for a, b in zip(zh, en)}
        fragment_maps["en", slug] = {b["id"]: a["id"] for a, b in zip(zh, en)}

    indexes = {}
    for directory, locale in (("", "zh-CN"), ("zh-CN", "zh-CN"), ("en", "en")):
        t = MESSAGES[locale]
        pages = LOCALES[locale]
        index: list[dict] = []
        for position, (slug, title, source, description) in enumerate(pages):
            content, tokens = documents[locale, slug]
            source_link = f"{REPOSITORY}/blob/main/{source}"
            neighbors = []
            for neighbor, label in ((position - 1, t["previous"]), (position + 1, t["next"])):
                if 0 <= neighbor < len(pages):
                    target, name, _, _ = pages[neighbor]
                    neighbors.append(
                        f'<a href="{target}.html"><small>{escape(label)}</small><span>{escape(name)} →</span></a>'
                    )
            body = f'''<div class="docs-layout shell">
              <aside class="sidebar" aria-label="{escape(t["doc_nav"])}"><details open><summary>{escape(t["doc_nav"])}</summary><nav>{sidebar(slug, locale)}</nav></details></aside>
              <main id="content" class="doc-main"><div class="doc-meta"><span class="mono">DOCUMENTATION / {slug.upper()}</span><a href="{source_link}">{escape(t["source_link"])}</a></div>
              <article class="prose">{content}</article>
              <nav class="page-neighbors" aria-label="{escape(t["neighbors"])}">{"".join(neighbors)}</nav></main>
              <aside class="page-toc" aria-label="{escape(t["toc"])}"><p class="sidebar-label">{escape(t["toc"])}</p><nav>{toc_links(tokens)}</nav><a class="back-top" href="#content">{escape(t["back_top"])}</a></aside>
            </div>'''
            write_page(
                f"{slug}.html",
                title,
                description,
                body,
                locale,
                directory=directory,
                current=slug,
                fragments=fragment_maps[locale, slug],
            )
            sections = SearchSections(f"{slug}.html", title)
            sections.feed(content)
            sections.flush()
            index.extend(sections.sections)
        start_source = pages[0][2]
        start_text = (ROOT / start_source).read_text(encoding="utf-8")
        quickstart = re.search(r"```python\n(.*?)```", start_text, flags=re.S)
        if quickstart is None:
            raise ValueError(f"{start_source}: missing Python quick-start example")
        code, _ = render_markdown(start_source, locale, f"```python\n{quickstart[1]}```")
        home_source = SOURCE / ("en/index.html" if locale == "en" else "index.html")
        home = home_source.read_text(encoding="utf-8").replace("{{QUICKSTART_CODE}}", code)
        write_page(
            "index.html", t["home_title"], t["home_description"], home, locale, directory=directory
        )
        not_found = f'<main id="content" class="shell not-found"><p class="eyebrow">404 / PAGE NOT FOUND</p><h1>{escape(t["not_found_heading"])}</h1><p>{escape(t["not_found_body"])}</p><a class="button" href="./">{escape(t["not_found_home"])}</a></main>'
        write_page(
            "404.html",
            t["not_found_title"],
            t["not_found_description"],
            not_found,
            locale,
            directory=directory,
        )
        (OUTPUT / directory / "search-index.json").write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8"
        )
        indexes[directory] = index
    (OUTPUT / ".nojekyll").touch()
    sitemap_pages = write_search_metadata()
    links = validate_build(indexes)
    print(
        f"Built {(len(PAGES) + 2) * len(indexes)} pages (zh-CN, en, and legacy Chinese URLs); "
        f"{len(indexes['zh-CN']) + len(indexes['en'])} bilingual search sections; "
        f"validated {links} local links; {sitemap_pages} sitemap URLs in {OUTPUT}"
    )


if __name__ == "__main__":
    build()
