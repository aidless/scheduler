def three_sum(nums):
    nums.sort()
    n = len(nums)
    result = []
    for i in range(n - 2):
        if nums[i] > 0:
            break
        if i > 0 and nums[i] == nums[i - 1]:
            continue
        left, right = i + 1, n - 1
        while left < right:
            total = nums[i] + nums[left] + nums[right]
            if total < 0:
                left += 1
            elif total > 0:
                right -= 1
            else:
                result.append([nums[i], nums[left], nums[right]])
                while left < right and nums[left] == nums[left + 1]:
                    left += 1
                while left < right and nums[right] == nums[right - 1]:
                    right -= 1
                left += 1
                right -= 1
    return result


assert sorted(tuple(sorted(t)) for t in three_sum([-1,0,1,2,-1,-4])) == [(-1,-1,2),(-1,0,1)]
assert sorted(tuple(sorted(t)) for t in three_sum([0,0,0])) == [(0,0,0)]
assert three_sum([1,2]) == []
assert sorted(tuple(sorted(t)) for t in three_sum([-2,0,1,1,2])) == [(-2,0,2),(-2,1,1)]
print('TESTS_OK')
