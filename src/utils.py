from collections import OrderedDict
from typing import Any, Hashable, Iterator


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


class TrieNode:
    MAX_CHILD_NODES_FOR_DICT = 10

    def __init__(self):
        self._is_end_of_word = False
        self._children: list[TrieNode | None] | dict[int:TrieNode] = {}
        self._number_of_children = 0
        self._use_dict = True

    def switch_to_dict(self):
        """If the number of children is low use a dict to save memory"""
        temp_dict: dict[int, TrieNode] = {}
        for idx, node in enumerate(self._children):
            if node is not None:
                temp_dict[idx] = node
        self._children = temp_dict
        self._use_dict = True

    def switch_to_list(self):
        """If num of children are high we will use a list to reduce cache misses"""
        temp_list: list[TrieNode | None] = [None] * 26
        for key, value in self._children.items():
            temp_list[key] = value
        self._children = temp_list
        self._use_dict = False

    def get_child(self, letter: str) -> "TrieNode" | None:
        """Get the child of the current node using its letter alias"""
        try:
            return self._children[ord(letter) - ord("a")]
        except (KeyError, IndexError):
            return None

    def set_child(self, letter: str) -> "TrieNode":
        """Make a child for the current node for the letter alias passed in"""
        child = self.get_child(letter)
        if child:
            return child

        self._children[ord(letter) - ord("a")] = TrieNode()
        self._number_of_children += 1

        # is children dense enough to use a list now?
        if self._number_of_children > TrieNode.MAX_CHILD_NODES_FOR_DICT:
            self.switch_to_list()

        return self.get_child(letter)

    def delete_child(self, letter: str):
        """Remove the child of the current node based on a letter alias"""
        child = self.get_child(letter)
        if not child:
            return

        if self._use_dict:
            del self._children[ord(letter) - ord("a")]
        else:
            self._children[ord(letter) - ord("a")] = None

        self._number_of_children -= 1

        # is children sparse enough to use a dict now?
        if self._number_of_children <= TrieNode.MAX_CHILD_NODES_FOR_DICT:
            self.switch_to_dict()

        for child in self.iter_children():
            if child:
                return
        self._has_children = False

    def set_is_end_of_word(self, is_end_of_word: bool):
        self._is_end_of_word = is_end_of_word

    def iter_children(self) -> Iterator[tuple[int, "TrieNode" | None]]:
        """Returns an iterator over the children of the current node"""
        if self._use_dict:
            for key, node in self._children.items():
                yield chr(key + ord("a")), node
        else:
            for idx, node in enumerate(self._children):
                if node:
                    yield chr(idx + ord("a")), node

    @property
    def is_end_of_word(self):
        return self._is_end_of_word

    @property
    def children(self):
        return self._children

    @property
    def number_of_children(self):
        return self._number_of_children


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def starts_with(self, prefix: str) -> list[str]:
        """Returns a list of strings that start with the provided prefix.
        Sorted by length then alphabetically
        """
        parent = self.root
        result = []

        for letter in prefix:
            parent = parent.get_child(letter)
            if parent is None:
                return result

        parents = [(prefix, parent)]

        while parents:
            new_parents = []
            for prefix, node in parents:
                if node.is_end_of_word:
                    result.append(prefix)
                for char, child in node.iter_children():
                    if child:
                        new_parents.append((prefix + char, child))

            parents = new_parents

        return result

    def insert(self, word: str):
        parent = self.root
        for letter in word:
            parent = parent.get_child(letter)
            if parent is None:
                parent = parent.set_child(letter)

        parent.set_is_end_of_word(True)

    def delete(self, word: str):
        letter_node_path = [(0, self.root)]
        for idx, letter in enumerate(word, start=1):
            child = letter_node_path[-1][1].get_child(letter)
            letter_node_path.append((idx, child))

        letter_node_path[-1][1].set_is_end_of_word(False)

        delete_child = False

        for idx, node in reversed(letter_node_path):
            if delete_child:
                node.delete_child(word[idx])
            if not (node._number_of_children > 0 or node.is_end_of_word):
                return
            delete_child = True
