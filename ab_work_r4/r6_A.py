def top_k_frequent(nums, k):
    from collections import Counter
    count = Counter(nums)
    return [item for item, _ in count.most_common(k)]


assert set(top_k_frequent([1,1,1,2,2,3], 2)) == {1,2}
assert set(top_k_frequent([1], 1)) == {1}
assert set(top_k_frequent([4,4,4,1,1,2], 2)) == {4,1}
print('TESTS_OK')
