class LRUCache:
    class _Node:
        __slots__ = ('key', 'value', 'prev', 'next')

        def __init__(self, key=0, value=0):
            self.key = key
            self.value = value
            self.prev = None
            self.next = None

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}
        self.head = self._Node()
        self.tail = self._Node()
        self.head.next = self.tail
        self.tail.prev = self.head

    def _remove(self, node: '_Node'):
        node.prev.next = node.next
        node.next.prev = node.prev

    def _add_to_head(self, node: '_Node'):
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node

    def get(self, key: int) -> int:
        if key in self.cache:
            node = self.cache[key]
            self._remove(node)
            self._add_to_head(node)
            return node.value
        return -1

    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            node = self.cache[key]
            node.value = value
            self._remove(node)
            self._add_to_head(node)
        else:
            if len(self.cache) >= self.capacity:
                lru = self.tail.prev
                self._remove(lru)
                del self.cache[lru.key]
            node = self._Node(key, value)
            self.cache[key] = node
            self._add_to_head(node)


c = LRUCache(2)
c.put(1,1)
c.put(2,2)
assert c.get(1) == 1
c.put(3,3)
assert c.get(2) == -1
c.put(4,4)
assert c.get(1) == -1
assert c.get(3) == 3
assert c.get(4) == 4
c2 = LRUCache(1)
c2.put(2,1)
assert c2.get(2) == 1
c2.put(3,1)
assert c2.get(2) == -1
assert c2.get(3) == 1
print('TESTS_OK')
