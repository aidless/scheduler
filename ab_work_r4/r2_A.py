def is_valid_parens(s):
    stack = []
    mapping = {')': '(', ']': '[', '}': '{'}
    for ch in s:
        if ch in mapping.values():
            stack.append(ch)
        elif ch in mapping:
            if not stack or stack.pop() != mapping[ch]:
                return False
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
