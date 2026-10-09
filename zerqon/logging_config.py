"""Yerel log dosyası yapılandırması. Gizli bilgiler log'a yazılmadan maskelenir."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # URL içindeki kullanıcı:şifre bilgisi
    (re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@", re.I), r"\g<scheme>***:***@"),
    # Sorgu parametrelerinde token/şifre benzeri değerler
    (
        re.compile(
            r"(?P<key>[?&](?:token|access_token|api_key|apikey|key|password|passwd|secret|session|sid|auth)=)[^&\s]+",
            re.I,
        ),
        r"\g<key>***",
    ),
    # Authorization / Cookie başlıkları
    (re.compile(r"(?P<key>(?:authorization|cookie|set-cookie)\s*[:=]\s*)[^\n]+", re.I), r"\g<key>***"),
]


def redact(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


_configured = False


def setup_logging(logs_dir: Path, level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = RedactingFormatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")

    file_handler = RotatingFileHandler(
        logs_dir / "zerqon.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger("zerqon")
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root.propagate = False
    _configured = True
