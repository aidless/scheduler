def length_of_longest_substring(s):
    last_seen = {}
    left = 0
    max_len = 0
    for right, ch in enumerate(s):
        if ch in last_seen and last_seen[ch] >= left:
            left = last_seen[ch] + 1
        last_seen[ch] = right
        max_len = max(max_len, right - left + 1)
    return max_len


assert length_of_longest_substring('abcabcbb') == 3
assert length_of_longest_substring('bbbbb') == 1
assert length_of_longest_substring('pwwkew') == 3
assert length_of_longest_substring('') == 0
assert length_of_longest_substring('au') == 2
print('TESTS_OK')
