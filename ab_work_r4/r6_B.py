from collections import Counter

def top_k_frequent(nums, k):
    return [item for item, _ in Counter(nums).most_common(k)]


assert set(top_k_frequent([1,1,1,2,2,3], 2)) == {1,2}
assert set(top_k_frequent([1], 1)) == {1}
assert set(top_k_frequent([4,4,4,1,1,2], 2)) == {4,1}
print('TESTS_OK')
