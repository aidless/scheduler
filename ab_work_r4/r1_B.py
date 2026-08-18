def length_of_longest_substring(s):
    char_index = {}
    max_length = 0
    left = 0
    for right, char in enumerate(s):
        if char in char_index and char_index[char] >= left:
            left = char_index[char] + 1
        char_index[char] = right
        max_length = max(max_length, right - left + 1)
    return max_length


assert length_of_longest_substring('abcabcbb') == 3
assert length_of_longest_substring('bbbbb') == 1
assert length_of_longest_substring('pwwkew') == 3
assert length_of_longest_substring('') == 0
assert length_of_longest_substring('au') == 2
print('TESTS_OK')
