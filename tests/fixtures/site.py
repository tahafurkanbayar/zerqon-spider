"""Testler için yerel web sitesi (üçüncü taraf sitelere bağımlılık yok).

Kasıtlı olarak çeşitli teknik SEO sorunları içerir.
"""

from __future__ import annotations

import gzip
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route


def page(title: str, body: str, head: str = "", lang: str = "tr") -> str:
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{title}</title>'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">{head}</head><body>{body}</body></html>'
    )


LOREM = " ".join(["Zerqon örnek içerik metni teknik SEO denetimi için yazılmıştır."] * 40)

HOME = page(
    "Ana Sayfa | Örnek Site",
    f"""
    <header><nav>
      <a href="/about">Hakkımızda</a>
      <a href="/blog/">Blog</a>
      <a href="/products?id=1">Ürün</a>
      <a href="/broken">Kırık</a>
      <a href="/redirect-1">Eski sayfa</a>
      <a href="/loop-a">Döngü</a>
      <a href="/private/secret">Gizli</a>
      <a href="/noindex-page">Noindex</a>
      <a href="/xrobots">XRobots</a>
      <a href="/canonical-other">Canonical diğer</a>
      <a href="/error">Hata</a>
      <a href="/deep/1">Derin</a>
      <a href="/js-page">JS sayfası</a>
      <a href="/about-copy">Kopya</a>
      <a href="/xss">XSS</a>
      <a href="/nofollow-target" rel="nofollow">Nofollow</a>
      <a href="https://external.example/page">Dış bağlantı</a>
      <a href="mailto:info@example.com">E-posta</a>
    </nav></header>
    <main><h1>Hoş geldiniz</h1><p>{LOREM}</p>
      <img src="/img/logo.png" alt="Logo" width="100" height="40">
      <img src="/img/missing.png">
      <img src="/img/big.jpg" alt="Büyük görsel" loading="lazy">
    </main>""",
    head='<meta name="description" content="Örnek site ana sayfa açıklaması: teknik SEO testleri için hazırlanmış yerel bir sitedir.">'
    '<link rel="canonical" href="/">'
    '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Örnek"}</script>',
)

ABOUT = page(
    "Hakkımızda | Örnek Site",
    f"<h1>Hakkımızda</h1><h3>Atlanan seviye</h3><p>{LOREM}</p><a href='/'>Ana sayfa</a>",
    head='<meta name="description" content="Kısa">',
)
ABOUT_COPY = page(
    "Hakkımızda | Örnek Site",
    f"<h1>Hakkımızda</h1><p>{LOREM}</p><a href='/'>Ana sayfa</a>",
)
BLOG = page("Blog", "<h1>Blog</h1><h1>İkinci H1</h1><p>Az içerik.</p><a href='/'>Ana</a>")
PRODUCT = page(
    "Ürün sayfası başlığı çok uzun olacak şekilde yazılmış bir başlık örneği ki eşik aşılsın",
    "<h1>Ürün</h1><p>Ürün açıklaması.</p>",
    head='<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product"}</script>'
    '<script type="application/ld+json">{ bozuk json </script>',
)
NOINDEX = page("Noindex", "<h1>Noindex</h1><p>x</p>", head='<meta name="robots" content="noindex, follow">')
CANONICAL_OTHER = page("Canonical diğer", "<h1>C</h1>", head='<link rel="canonical" href="/about">')
ORPHAN = page("Yetim", "<h1>Yetim sayfa</h1><p>Hiçbir yerden bağlantı almaz.</p>")
JS_PAGE = page(
    "JS",
    '<div id="root"></div><script>document.getElementById("root").innerHTML='
    "'<h1>Render edilmiş başlık</h1><p>' + 'JavaScript ile oluşturulan içerik. '.repeat(30) + '</p><a href=\"/js-only-link\">JS bağlantısı</a>';"
    "</script><script></script><script></script>",
)
JS_ONLY = page("JS hedef", "<h1>JS ile keşfedilen sayfa</h1>")
XSS_PAGE = page(
    "<script>alert('xss-title')</script>",
    "<h1><img src=x onerror=alert(1)>Başlık</h1>",
    head='<meta name="description" content="=HYPERLINK(&quot;http://evil.example&quot;)">',
)

SITEMAP_PAGES = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>{base}/about</loc></url>
  <url><loc>{base}/orphan</loc></url>
  <url><loc>{base}/noindex-page</loc></url>
</urlset>"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>{base}/sitemap-pages.xml.gz</loc></sitemap>
</sitemapindex>"""

ROBOTS = "User-agent: *\nDisallow: /private/\n\nSitemap: {base}/sitemap_index.xml\n"

_hits: dict[str, int] = {}


def build_app() -> Starlette:
    def base(request: Request) -> str:
        return f"{request.url.scheme}://{request.url.netloc}"

    async def home(request: Request) -> Response:
        return HTMLResponse(HOME)

    async def robots(request: Request) -> Response:
        return PlainTextResponse(ROBOTS.format(base=base(request)))

    async def sitemap_index(request: Request) -> Response:
        return Response(SITEMAP_INDEX.format(base=base(request)), media_type="application/xml")

    async def sitemap_pages(request: Request) -> Response:
        data = gzip.compress(SITEMAP_PAGES.format(base=base(request)).encode())
        return Response(data, media_type="application/gzip")

    def html(content: str, status: int = 200, headers: dict[str, str] | None = None) -> Response:
        return HTMLResponse(content, status_code=status, headers=headers)

    async def deep(request: Request) -> Response:
        n = int(request.path_params["n"])
        return HTMLResponse(page(f"Derin {n}", f"<h1>Derin {n}</h1><p>{LOREM}</p><a href='/deep/{n + 1}'>Sonraki</a>"))

    async def throttled(request: Request) -> Response:
        _hits["429"] = _hits.get("429", 0) + 1
        if _hits["429"] == 1:
            return PlainTextResponse("yavaş", status_code=429, headers={"Retry-After": "1"})
        return HTMLResponse(page("Sonunda", "<h1>Tamam</h1>"))

    async def image(request: Request) -> Response:
        name = request.path_params["name"]
        if name == "logo.png":
            return Response(b"\x89PNG" + b"0" * 2000, media_type="image/png")
        if name == "big.jpg":
            return Response(b"\xff\xd8" + b"0" * 300_000, media_type="image/jpeg")
        return PlainTextResponse("yok", status_code=404)

    routes = [
        Route("/", home),
        Route("/robots.txt", robots),
        Route("/sitemap_index.xml", sitemap_index),
        Route("/sitemap-pages.xml.gz", sitemap_pages),
        Route("/about", lambda r: html(ABOUT)),
        Route("/about-copy", lambda r: html(ABOUT_COPY)),
        Route("/blog/", lambda r: html(BLOG)),
        Route("/products", lambda r: html(PRODUCT)),
        Route("/broken", lambda r: html(page("404", "<h1>Bulunamadı</h1>"), 404)),
        Route("/error", lambda r: html(page("500", "<h1>Hata</h1>"), 500)),
        Route("/redirect-1", lambda r: RedirectResponse("/redirect-2", status_code=301)),
        Route("/redirect-2", lambda r: RedirectResponse("/about", status_code=302)),
        Route("/loop-a", lambda r: RedirectResponse("/loop-b", status_code=301)),
        Route("/loop-b", lambda r: RedirectResponse("/loop-a", status_code=301)),
        Route("/private/secret", lambda r: html(page("Gizli", "<h1>Gizli</h1>"))),
        Route("/noindex-page", lambda r: html(NOINDEX)),
        Route("/xrobots", lambda r: html(page("X", "<h1>X</h1>"), headers={"X-Robots-Tag": "noindex"})),
        Route("/canonical-other", lambda r: html(CANONICAL_OTHER)),
        Route("/orphan", lambda r: html(ORPHAN)),
        Route("/nofollow-target", lambda r: html(page("NF", "<h1>NF</h1>"))),
        Route("/js-page", lambda r: html(JS_PAGE)),
        Route("/js-only-link", lambda r: html(JS_ONLY)),
        Route("/xss", lambda r: html(XSS_PAGE)),
        Route("/deep/{n:int}", deep),
        Route("/throttled", throttled),
        Route("/img/{name}", image),
    ]
    return Starlette(routes=routes)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def serve_site() -> Iterator[str]:
    _hits.clear()
    port = _free_port()
    config = uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(5)
