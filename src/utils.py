from collections import OrderedDict
from typing import Any, Hashable


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