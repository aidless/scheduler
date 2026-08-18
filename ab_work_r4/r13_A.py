class Trie:
    def __init__(self):
        self.children = {}
        self.is_end = False

    def insert(self, word: str) -> None:
        node = self
        for ch in word:
            if ch not in node.children:
                node.children[ch] = Trie()
            node = node.children[ch]
        node.is_end = True

    def search(self, word: str) -> bool:
        node = self._find(word)
        return node is not None and node.is_end

    def starts_with(self, prefix: str) -> bool:
        return self._find(prefix) is not None

    def _find(self, s: str):
        node = self
        for ch in s:
            if ch not in node.children:
                return None
            node = node.children[ch]
        return node


t = Trie()
t.insert('apple')
assert t.search('apple') is True
assert t.search('app') is False
assert t.starts_with('app') is True
t.insert('app')
assert t.search('app') is True
t2 = Trie()
assert t2.search('x') is False
t2.insert('ab')
assert t2.starts_with('abc') is False
print('TESTS_OK')
