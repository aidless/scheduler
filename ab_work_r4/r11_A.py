def longest_palindromic_substring(s):
    if not s:
        return ""

    n = len(s)
    start, max_len = 0, 1

    def expand(left, right):
        while left >= 0 and right < n and s[left] == s[right]:
            left -= 1
            right += 1
        return left + 1, right - left - 1

    for i in range(n):
        l1, len1 = expand(i, i)
        l2, len2 = expand(i, i + 1)
        if len1 > max_len:
            start, max_len = l1, len1
        if len2 > max_len:
            start, max_len = l2, len2

    return s[start:start + max_len]


s='babad'; r=longest_palindromic_substring(s); assert r == r[::-1] and r in s and len(r) == 3
assert longest_palindromic_substring('cbbd') == 'bb'
assert longest_palindromic_substring('a') == 'a'
assert longest_palindromic_substring('') == ''
print('TESTS_OK')
