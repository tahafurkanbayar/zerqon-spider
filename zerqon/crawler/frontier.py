"""URL kuyruğu ve tekilleştirme (checkpoint DB'de, bkz. ADR-004).

- Öncelik: (derinlik, sıra) → genişlik-öncelikli (BFS) tarama.
- `seen` kümesi url_key'leri tutar; aynı URL'nin farklı yazımları tekrar taranmaz.
- Toplam kabul edilen URL sayısı `max_urls` ile sınırlıdır ve ASLA aşılmaz.
- Sitemap URL'leri "ertelenmiş" tutulur; bağlantı keşfi bittiğinde kuyruğa alınır.
"""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass, field


@dataclass(order=True)
class FrontierItem:
    depth: int
    seq: int
    url: str = field(compare=False)
    key: str = field(compare=False)
    source: str = field(compare=False, default="link")


class Frontier:
    def __init__(self, max_urls: int) -> None:
        self.max_urls = max_urls
        self.queue: asyncio.PriorityQueue[FrontierItem] = asyncio.PriorityQueue()
        self.seen: set[str] = set()
        self.accepted = 0
        self.limit_reached = False
        self.deferred: list[tuple[str, str]] = []  # (url, key) sitemap kaynaklı
        self.new_items: list[FrontierItem] = []  # DB'ye yazılmayı bekleyenler
        self._seq = itertools.count()

    def __len__(self) -> int:
        return self.queue.qsize()

    def has_capacity(self) -> bool:
        return self.accepted < self.max_urls

    def add(self, url: str, key: str, depth: int, source: str) -> bool:
        if key in self.seen:
            return False
        if not self.has_capacity():
            self.limit_reached = True
            return False
        self.seen.add(key)
        self.accepted += 1
        item = FrontierItem(depth, next(self._seq), url, key, source)
        self.queue.put_nowait(item)
        self.new_items.append(item)
        return True

    def defer(self, url: str, key: str) -> None:
        if key not in self.seen:
            self.deferred.append((url, key))

    def release_deferred(self, depth: int = 1) -> int:
        added = 0
        for url, key in self.deferred:
            if self.add(url, key, depth, "sitemap"):
                added += 1
            elif not self.has_capacity():
                break
        self.deferred.clear()
        return added

    def restore(self, pending: list[tuple[str, str, int, str]], all_keys: set[str]) -> None:
        """Devam ettirme: DB'deki tüm anahtarlar görüldü sayılır, bekleyenler kuyruğa alınır."""
        self.seen = set(all_keys)
        self.accepted = len(all_keys)
        for url, key, depth, source in pending:
            self.queue.put_nowait(FrontierItem(depth, next(self._seq), url, key, source))

    def drain_new(self) -> list[FrontierItem]:
        items, self.new_items = self.new_items, []
        return items
