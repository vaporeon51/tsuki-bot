from collections import OrderedDict
from collections.abc import Mapping
from typing import Any, Hashable

from discord import Message


class LRUCache:
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key: Hashable) -> Any:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)  # Update the order to reflect recent access
        return self.cache[key]

    def put(self, key: Hashable, value: Any) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)  # Update the order to reflect recent insertion
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)  # Remove the first inserted (least recently used) item

    def invalidate(self, key: Hashable) -> None:
        if key in self.cache:
            del self.cache[key]


def is_message_broken_link(message: Message | Mapping[str, Any]) -> bool:
    """Return whether Discord has produced an embed that shows an Imgur link is broken.

    An empty embed list means Discord has not unfurled the URL yet, not that the
    URL is dead.
    """

    embeds = message.get("embeds", []) if isinstance(message, Mapping) else message.embeds
    if not embeds:
        return False

    first_embed = embeds[0]
    embed_type = first_embed.get("type") if isinstance(first_embed, Mapping) else first_embed.type
    if embed_type == "article":
        return True

    return False
