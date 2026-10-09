"""hreflang değer doğrulaması (BCP 47 biçimi + bilinen yaygın hatalar).

Not: Tam ISO 639-1 / ISO 3166-1 tablosu yerine biçim doğrulaması yapılır;
sık görülen hatalı kodlar ayrıca yakalanır. Sınırlama README'de belgelenmiştir.
"""

from __future__ import annotations

import re

_PATTERN = re.compile(r"^(?P<lang>[a-z]{2,3})(?:-(?P<script>[a-z]{4}))?(?:-(?P<region>[a-z]{2}|\d{3}))?$", re.I)

# Dil alanında sık kullanılan ama dil kodu olmayan (ülke kodu) değerler
_NOT_LANGUAGES = frozenset({"jp", "cn", "dk", "gr", "cz", "ua", "us", "gb", "ir", "vn", "il", "at", "mx"})
# Bölge alanında sık kullanılan hatalı değerler
_BAD_REGIONS = frozenset({"uk", "en", "eu", "la"})


def is_valid_hreflang(value: str) -> bool:
    value = value.strip()
    if value.lower() == "x-default":
        return True
    match = _PATTERN.match(value)
    if not match:
        return False
    if match.group("lang").lower() in _NOT_LANGUAGES:
        return False
    region = match.group("region")
    return not (region and region.lower() in _BAD_REGIONS)
