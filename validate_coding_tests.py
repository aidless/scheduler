"""coding_ab_tasks.json 断言自校验：用参考实现跑全部断言，确认测试本身正确。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

REFS = {
    "is_palindrome": "def is_palindrome(s):\n    return s == s[::-1]\n",
    "fizzbuzz": (
        "def fizzbuzz(n):\n"
        "    out = []\n"
        "    for i in range(1, n + 1):\n"
        "        if i % 15 == 0:\n            out.append('FizzBuzz')\n"
        "        elif i % 3 == 0:\n            out.append('Fizz')\n"
        "        elif i % 5 == 0:\n            out.append('Buzz')\n"
        "        else:\n            out.append(str(i))\n"
        "    return out\n"
    ),
    "flatten": (
        "def flatten(nested):\n"
        "    out = []\n"
        "    for x in nested:\n"
        "        if isinstance(x, list):\n            out.extend(flatten(x))\n"
        "        else:\n            out.append(x)\n"
        "    return out\n"
    ),
    "binary_search": (
        "def binary_search(sorted_list, target):\n"
        "    lo, hi = 0, len(sorted_list) - 1\n"
        "    while lo <= hi:\n"
        "        mid = (lo + hi) // 2\n"
        "        if sorted_list[mid] == target:\n            return mid\n"
        "        elif sorted_list[mid] < target:\n            lo = mid + 1\n"
        "        else:\n            hi = mid - 1\n"
        "    return -1\n"
    ),
    "word_count": (
        "def word_count(text):\n"
        "    d = {}\n"
        "    for w in text.split():\n        d[w] = d.get(w, 0) + 1\n"
        "    return d\n"
    ),
    "clamp": "def clamp(x, lo, hi):\n    return max(lo, min(hi, x))\n",
}


def main() -> int:
    import json
    spec = json.loads((HERE / "coding_ab_tasks.json").read_text(encoding="utf-8"))
    all_pass = True
    for t in spec["tasks"]:
        code = REFS[t["name"]] + "\n\n" + "\n".join(t["tests"]) + "\nprint('TESTS_OK')\n"
        fd, fn = tempfile.mkstemp(suffix=".py", text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        r = subprocess.run([sys.executable, fn], capture_output=True,
                           text=True, timeout=20)
        ok = r.returncode == 0 and "TESTS_OK" in r.stdout
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL"), t["id"], t["name"],
              "" if ok else r.stderr[:200])
        os.unlink(fn)
    print("ALL_TESTS_VALID" if all_pass else "TESTS_BROKEN")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
