def longest_palindromic_substring(s):
    if not s:
        return ""

    start, end = 0, 0

    def expand_around_center(left, right):
        while left >= 0 and right < len(s) and s[left] == s[right]:
            left -= 1
            right += 1
        return left + 1, right - 1

    for i in range(len(s)):
        l1, r1 = expand_around_center(i, i)
        l2, r2 = expand_around_center(i, i + 1)

        if r1 - l1 > end - start:
            start, end = l1, r1
        if r2 - l2 > end - start:
            start, end = l2, r2

    return s[start:end + 1]


s='babad'; r=longest_palindromic_substring(s); assert r == r[::-1] and r in s and len(r) == 3
assert longest_palindromic_substring('cbbd') == 'bb'
assert longest_palindromic_substring('a') == 'a'
assert longest_palindromic_substring('') == ''
print('TESTS_OK')
