"""robots.txt ayrıştırıcı ve eşleştirici (RFC 9309 + Google davranışı, bkz. ADR-007).

- User-agent eşleşmesi: ürün belirteci (ilk '/' öncesi) büyük/küçük harf duyarsız, en uzun eşleşen grup;
  hiçbiri eşleşmezse '*' grubu.
- Aynı user-agent için birden çok grup birleştirilir.
- Kural eşleşmesi: '*' joker, '$' satır sonu; en uzun (en spesifik) kural kazanır, eşitlikte Allow.
- '/robots.txt' her zaman izinlidir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import quote, unquote, urlsplit

MAX_ROBOTS_BYTES = 500 * 1024  # Google 500 KiB sınırı


class RobotsStatus(StrEnum):
    OK = "ok"  # 2xx, ayrıştırıldı
    NOT_FOUND = "not_found"  # 4xx → kısıtlama yok
    UNAVAILABLE = "unavailable"  # 5xx / ağ hatası → tamamen engelli (temkinli)
    BLOCKED = "blocked_security"


@dataclass(frozen=True)
class Rule:
    allow: bool
    path: str
    regex: re.Pattern[str]

    @property
    def specificity(self) -> int:
        return len(self.path)


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


def _normalize_path(path: str) -> str:
    # Yüzde kodlamayı tutarlı hale getir (ayrılmış karakterler korunur)
    return quote(unquote(path), safe="/*$?=&;:@!,+%-._~'()")


def _compile_rule(path: str) -> re.Pattern[str]:
    path = _normalize_path(path)
    anchored = path.endswith("$")
    if anchored:
        path = path[:-1]
    pattern = "".join(".*" if ch == "*" else re.escape(ch) for ch in path)
    return re.compile(pattern + ("$" if anchored else ""))


@dataclass
class RobotsTxt:
    groups: list[Group] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    status: RobotsStatus = RobotsStatus.OK
    raw_size: int = 0

    @classmethod
    def allow_all(cls, status: RobotsStatus = RobotsStatus.NOT_FOUND) -> RobotsTxt:
        return cls(status=status)

    @classmethod
    def disallow_all(cls, status: RobotsStatus = RobotsStatus.UNAVAILABLE) -> RobotsTxt:
        group = Group(agents=["*"], rules=[Rule(False, "/", _compile_rule("/"))])
        return cls(groups=[group], status=status)

    @classmethod
    def parse(cls, text: str) -> RobotsTxt:
        text = text[:MAX_ROBOTS_BYTES]
        robots = cls(raw_size=len(text))
        current: Group | None = None
        last_was_agent = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = Group()
                    robots.groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            if key == "sitemap":
                if value:
                    robots.sitemaps.append(value)
                continue
            last_was_agent = False
            if current is None:
                continue
            if key in ("allow", "disallow"):
                if not value:
                    continue  # boş Disallow = kısıtlama yok
                if not value.startswith(("/", "*")):
                    value = "/" + value
                current.rules.append(Rule(key == "allow", value, _compile_rule(value)))
            elif key == "crawl-delay":
                try:
                    current.crawl_delay = max(0.0, float(value))
                except ValueError:
                    pass
        return robots

    def _groups_for(self, user_agent: str) -> list[Group]:
        token = user_agent.strip().lower()
        # "Mozilla/5.0 (compatible; ZerqonSpider/1.0 ...)" → ürün belirteçleri
        cleaned = re.sub(r"\S+://\S+", " ", token)
        tokens = set(re.findall(r"([a-z0-9_-]+)/[\w.]+", cleaned))
        first = re.match(r"[a-z0-9_-]+", cleaned)
        if first:
            tokens.add(first.group(0))
        best_len = 0
        matched: list[Group] = []
        for group in self.groups:
            for agent in group.agents:
                if agent == "*":
                    continue
                if agent in tokens:
                    if len(agent) > best_len:
                        best_len, matched = len(agent), [group]
                    elif len(agent) == best_len and group not in matched:
                        matched.append(group)
        if matched:
            return matched
        return [g for g in self.groups if "*" in g.agents]

    def _rules_for(self, user_agent: str) -> list[Rule]:
        return [rule for group in self._groups_for(user_agent) for rule in group.rules]

    def crawl_delay(self, user_agent: str) -> float | None:
        delays = [g.crawl_delay for g in self._groups_for(user_agent) if g.crawl_delay is not None]
        return max(delays) if delays else None

    def matching_rule(self, url: str, user_agent: str) -> Rule | None:
        parts = urlsplit(url)
        path = _normalize_path(parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if path == "/robots.txt":
            return None
        best: Rule | None = None
        for rule in self._rules_for(user_agent):
            if rule.regex.match(path):
                if best is None or rule.specificity > best.specificity or (
                    rule.specificity == best.specificity and rule.allow and not best.allow
                ):
                    best = rule
        return best

    def is_allowed(self, url: str, user_agent: str) -> bool:
        rule = self.matching_rule(url, user_agent)
        return rule is None or rule.allow


def robots_url_for(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"
