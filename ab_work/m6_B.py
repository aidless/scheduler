def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


assert clamp(5, 0, 10) == 5
assert clamp(-3, 0, 10) == 0
assert clamp(15, 0, 10) == 10
assert clamp(0, 0, 10) == 0
print('TESTS_OK')
