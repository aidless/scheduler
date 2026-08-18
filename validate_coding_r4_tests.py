"""fleet-r4 任务集断言自校验：参考实现 + 逐任务断言，ALL PASS 才允许进 A/B。

用法: python validate_coding_r4_tests.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

REFS = {
    "r1": (
        "def length_of_longest_substring(s):\n"
        "    last = {}\n    start = 0\n    best = 0\n"
        "    for i, ch in enumerate(s):\n"
        "        if ch in last and last[ch] >= start:\n            start = last[ch] + 1\n"
        "        last[ch] = i\n        best = max(best, i - start + 1)\n"
        "    return best\n"
    ),
    "r2": (
        "def is_valid_parens(s):\n"
        "    pairs = {')': '(', ']': '[', '}': '{'}\n    stack = []\n"
        "    for ch in s:\n"
        "        if ch in '([{':\n            stack.append(ch)\n"
        "        else:\n"
        "            if not stack or stack[-1] != pairs.get(ch):\n                return False\n"
        "            stack.pop()\n"
        "    return not stack\n"
    ),
    "r3": (
        "def three_sum(nums):\n"
        "    nums = sorted(nums)\n    res = []\n    n = len(nums)\n"
        "    for i in range(n - 2):\n"
        "        if i > 0 and nums[i] == nums[i - 1]:\n            continue\n"
        "        lo, hi = i + 1, n - 1\n"
        "        while lo < hi:\n"
        "            s = nums[i] + nums[lo] + nums[hi]\n"
        "            if s == 0:\n"
        "                res.append([nums[i], nums[lo], nums[hi]])\n"
        "                while lo < hi and nums[lo] == nums[lo + 1]:\n                    lo += 1\n"
        "                while lo < hi and nums[hi] == nums[hi - 1]:\n                    hi -= 1\n"
        "                lo += 1\n                hi -= 1\n"
        "            elif s < 0:\n                lo += 1\n"
        "            else:\n                hi -= 1\n"
        "    return res\n"
    ),
    "r4": (
        "def merge_intervals(intervals):\n"
        "    if not intervals:\n        return []\n"
        "    intervals = sorted(intervals, key=lambda x: x[0])\n"
        "    res = [list(intervals[0])]\n"
        "    for start, end in intervals[1:]:\n"
        "        if start <= res[-1][1]:\n            res[-1][1] = max(res[-1][1], end)\n"
        "        else:\n            res.append([start, end])\n"
        "    return res\n"
    ),
    "r5": (
        "def group_anagrams(strs):\n"
        "    from collections import defaultdict\n"
        "    d = defaultdict(list)\n"
        "    for s in strs:\n        d[tuple(sorted(s))].append(s)\n"
        "    return list(d.values())\n"
    ),
    "r6": (
        "def top_k_frequent(nums, k):\n"
        "    from collections import Counter\n"
        "    cnt = Counter(nums)\n"
        "    return [x for x, _ in cnt.most_common(k)]\n"
    ),
    "r7": (
        "def eval_rpn(tokens):\n"
        "    stack = []\n"
        "    ops = {'+': lambda a, b: a + b, '-': lambda a, b: a - b,\n"
        "           '*': lambda a, b: a * b, '/': lambda a, b: int(a / b)}\n"
        "    for t in tokens:\n"
        "        if t in ops:\n"
        "            b = stack.pop()\n            a = stack.pop()\n"
        "            stack.append(ops[t](a, b))\n"
        "        else:\n            stack.append(int(t))\n"
        "    return stack[-1]\n"
    ),
    "r8": (
        "def min_edit_distance(word1, word2):\n"
        "    m, n = len(word1), len(word2)\n"
        "    dp = list(range(n + 1))\n"
        "    for i in range(1, m + 1):\n"
        "        prev = dp[0]\n        dp[0] = i\n"
        "        for j in range(1, n + 1):\n"
        "            tmp = dp[j]\n"
        "            if word1[i - 1] == word2[j - 1]:\n                dp[j] = prev\n"
        "            else:\n                dp[j] = 1 + min(prev, dp[j], dp[j - 1])\n"
        "            prev = tmp\n"
        "    return dp[n]\n"
    ),
    "r9": (
        "def trap(height):\n"
        "    if not height:\n        return 0\n"
        "    left, right = 0, len(height) - 1\n"
        "    lmax = rmax = 0\n    water = 0\n"
        "    while left < right:\n"
        "        if height[left] < height[right]:\n"
        "            if height[left] >= lmax:\n                lmax = height[left]\n"
        "            else:\n                water += lmax - height[left]\n"
        "            left += 1\n"
        "        else:\n"
        "            if height[right] >= rmax:\n                rmax = height[right]\n"
        "            else:\n                water += rmax - height[right]\n"
        "            right -= 1\n"
        "    return water\n"
    ),
    "r10": (
        "def coin_change(coins, amount):\n"
        "    INF = float('inf')\n"
        "    dp = [0] + [INF] * amount\n"
        "    for a in range(1, amount + 1):\n"
        "        for c in coins:\n"
        "            if c <= a and dp[a - c] + 1 < dp[a]:\n                dp[a] = dp[a - c] + 1\n"
        "    return dp[amount] if dp[amount] != INF else -1\n"
    ),
    "r11": (
        "def longest_palindromic_substring(s):\n"
        "    if not s:\n        return ''\n"
        "    start, end = 0, 0\n"
        "    def expand(l, r):\n"
        "        while l >= 0 and r < len(s) and s[l] == s[r]:\n"
        "            l -= 1\n            r += 1\n"
        "        return l + 1, r - 1\n"
        "    for i in range(len(s)):\n"
        "        l1, r1 = expand(i, i)\n"
        "        l2, r2 = expand(i, i + 1)\n"
        "        if r1 - l1 > end - start:\n            start, end = l1, r1\n"
        "        if r2 - l2 > end - start:\n            start, end = l2, r2\n"
        "    return s[start:end + 1]\n"
    ),
    "r12": (
        "class LRUCache:\n"
        "    def __init__(self, capacity):\n"
        "        from collections import OrderedDict\n"
        "        self.cap = capacity\n        self.d = OrderedDict()\n"
        "    def get(self, key):\n"
        "        if key not in self.d:\n            return -1\n"
        "        self.d.move_to_end(key)\n        return self.d[key]\n"
        "    def put(self, key, value):\n"
        "        if key in self.d:\n            self.d.move_to_end(key)\n"
        "        self.d[key] = value\n"
        "        if len(self.d) > self.cap:\n            self.d.popitem(last=False)\n"
    ),
    "r13": (
        "class Trie:\n"
        "    def __init__(self):\n        self.children = {}\n        self.is_end = False\n"
        "    def insert(self, word):\n"
        "        node = self\n"
        "        for ch in word:\n"
        "            if ch not in node.children:\n                node.children[ch] = Trie()\n"
        "            node = node.children[ch]\n"
        "        node.is_end = True\n"
        "    def search(self, word):\n"
        "        node = self._find(word)\n"
        "        return node is not None and node.is_end\n"
        "    def starts_with(self, prefix):\n"
        "        return self._find(prefix) is not None\n"
        "    def _find(self, prefix):\n"
        "        node = self\n"
        "        for ch in prefix:\n"
        "            if ch not in node.children:\n                return None\n"
        "            node = node.children[ch]\n"
        "        return node\n"
    ),
    "r14": (
        "def num_islands(grid):\n"
        "    if not grid:\n        return 0\n"
        "    rows, cols = len(grid), len(grid[0])\n    count = 0\n"
        "    def dfs(r, c):\n"
        "        if r < 0 or r >= rows or c < 0 or c >= cols or grid[r][c] != '1':\n"
        "            return\n"
        "        grid[r][c] = '#'\n"
        "        dfs(r + 1, c)\n        dfs(r - 1, c)\n        dfs(r, c + 1)\n        dfs(r, c - 1)\n"
        "    for r in range(rows):\n"
        "        for c in range(cols):\n"
        "            if grid[r][c] == '1':\n                count += 1\n                dfs(r, c)\n"
        "    return count\n"
    ),
    "r15": (
        "def course_schedule(num_courses, prerequisites):\n"
        "    from collections import defaultdict, deque\n"
        "    graph = defaultdict(list)\n    indeg = [0] * num_courses\n"
        "    for a, b in prerequisites:\n        graph[b].append(a)\n        indeg[a] += 1\n"
        "    q = deque(i for i in range(num_courses) if indeg[i] == 0)\n"
        "    seen = 0\n"
        "    while q:\n"
        "        u = q.popleft()\n        seen += 1\n"
        "        for v in graph[u]:\n            indeg[v] -= 1\n"
        "            if indeg[v] == 0:\n                q.append(v)\n"
        "    return seen == num_courses\n"
    ),
    "r16": (
        "def max_subarray(nums):\n"
        "    best = cur = nums[0]\n"
        "    for x in nums[1:]:\n        cur = max(x, cur + x)\n        best = max(best, cur)\n"
        "    return best\n"
    ),
}


def main() -> int:
    spec = json.loads((HERE / "coding_r4_tasks.json").read_text(encoding="utf-8"))
    tasks = spec["tasks"]
    all_pass = True
    for task in tasks:
        tid = task["id"]
        ref = REFS.get(tid)
        if ref is None:
            print("MISSING-REF", tid)
            all_pass = False
            continue
        code = ref + "\n\n" + "\n".join(task["tests"]) + "\nprint('TESTS_OK')\n"
        fd, fn = tempfile.mkstemp(suffix=".py", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(code)
            proc = subprocess.run([sys.executable, fn], capture_output=True,
                                  text=True, timeout=30)
            ok = proc.returncode == 0 and "TESTS_OK" in proc.stdout
        finally:
            os.unlink(fn)
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL"), tid, task["name"],
              "" if ok else proc.stderr.strip()[:200])
    print("ALL_TESTS_VALID" if all_pass else "TESTS_BROKEN")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
