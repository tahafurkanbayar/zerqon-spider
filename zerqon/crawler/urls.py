"""URL çözümleme ve normalizasyon.

`url_key`, tekilleştirme için kullanılan kanonik anahtardır (bkz. ADR-009):
- şema ve host küçük harf, IDN → punycode
- varsayılan port (80/443) atılır
- fragment atılır
- boş path → "/" ; nokta segmentleri çözülür
- yüzde-kodlama normalize edilir (ayrılmamış karakterler çözülür, hex büyük harf)
- sorgu parametre sırası KORUNUR
"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_URL_LENGTH = 4096

_PCT_RE = re.compile(r"%([0-9A-Fa-f]{2})")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_PATH_SAFE = "/:@!$&'()*+,;=-._~%"
_QUERY_SAFE = "/?:@!$&'()*+,;=-._~%"


class InvalidURLError(ValueError):
    pass


def _normalize_percent(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else f"%{match.group(1).upper()}"

    return _PCT_RE.sub(repl, value)


def _encode_host(host: str) -> str:
    host = host.strip().rstrip(".").lower()
    if not host:
        return host
    if host.startswith("["):  # IPv6
        return host
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _remove_dot_segments(path: str) -> str:
    if not path:
        return "/"
    trailing = path.endswith("/") or path.endswith("/.") or path.endswith("/..")
    normalized = posixpath.normpath(path)
    if normalized == ".":
        normalized = "/"
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    normalized = re.sub(r"^/+", "/", normalized)
    if trailing and not normalized.endswith("/"):
        normalized += "/"
    return normalized


def normalize_url(url: str) -> str:
    """Getirilebilir, temizlenmiş mutlak URL döndürür (fragment yok)."""
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        raise InvalidURLError("URL çok uzun")
    if any(ord(ch) < 32 for ch in url):
        url = re.sub(r"[\x00-\x1f]", "", url)
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise InvalidURLError(f"URL ayrıştırılamadı: {exc}") from exc
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise InvalidURLError(f"Desteklenmeyen şema: {scheme or '(yok)'}")
    try:
        hostname = parts.hostname or ""
        port = parts.port
    except ValueError as exc:
        raise InvalidURLError(f"Geçersiz host/port: {exc}") from exc
    if not hostname:
        raise InvalidURLError("URL'de host bulunamadı")
    host = _encode_host(hostname)
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = quote(_normalize_percent(parts.path), safe=_PATH_SAFE)
    path = _remove_dot_segments(path)
    query = quote(_normalize_percent(parts.query), safe=_QUERY_SAFE)
    return urlunsplit((scheme, host, path, query, ""))


def url_key(url: str) -> str:
    """Tekilleştirme anahtarı. Geçersiz URL için ham değeri döndürür (kayıt amaçlı)."""
    try:
        return normalize_url(url)
    except InvalidURLError:
        return url.strip()


def resolve_url(base: str, href: str) -> str | None:
    """Sayfa içindeki bir bağlantıyı mutlak, normalize URL'ye çevirir; desteklenmeyenlerde None."""
    href = (href or "").strip()
    if not href or href.startswith("#"):
        return None
    lowered = href[:16].lower()
    if lowered.startswith(("javascript:", "mailto:", "tel:", "data:", "sms:", "ftp:", "file:", "blob:")):
        return None
    try:
        return normalize_url(urljoin(base, href))
    except (InvalidURLError, ValueError):
        return None


def validate_start_url(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.username or parts.password:
        raise InvalidURLError("URL içinde kullanıcı adı/şifre kabul edilmez")
    return normalize_url(value)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def has_query(url: str) -> bool:
    return bool(urlsplit(url).query)


def variant_signature(url: str) -> str:
    """URL varyasyonlarını gruplamak için gevşek imza: şema, www, büyük/küçük harf,
    sondaki '/', index dosyası ve parametre sırası farkları yok sayılır."""
    parts = urlsplit(url_key(url))
    host = strip_www((parts.hostname or "").lower())
    path = unquote(parts.path).lower()
    path = re.sub(r"/(index|default)\.(html?|php|aspx?)$", "/", path)
    path = path.rstrip("/") or "/"
    query = "&".join(sorted(q for q in parts.query.split("&") if q))
    return f"{host}{path}?{query}" if query else f"{host}{path}"
