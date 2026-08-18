def is_palindrome(s):
    return s == s[::-1]


assert is_palindrome('abcba') is True
assert is_palindrome('ab') is False
assert is_palindrome('') is True
assert is_palindrome('Aa') is False
print('TESTS_OK')
