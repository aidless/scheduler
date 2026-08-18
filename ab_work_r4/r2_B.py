def is_valid_parens(s):
    stack = []
    pairs = {')': '(', ']': '[', '}': '{'}
    for ch in s:
        if ch in pairs.values():
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack[-1] != pairs[ch]:
                return False
            stack.pop()
        else:
            return False
    return not stack


assert is_valid_parens('()') is True
assert is_valid_parens('()[]{}') is True
assert is_valid_parens('(]') is False
assert is_valid_parens('([)]') is False
assert is_valid_parens('') is True
assert is_valid_parens('(') is False
print('TESTS_OK')
