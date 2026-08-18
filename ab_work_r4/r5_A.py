def group_anagrams(strs):
    groups = {}
    for s in strs:
        key = ''.join(sorted(s))
        groups.setdefault(key, []).append(s)
    return list(groups.values())


assert sorted(tuple(sorted(g)) for g in group_anagrams(['eat','tea','tan','ate','nat','bat'])) == [('ate','eat','tea'),('bat',),('nat','tan')]
assert sorted(tuple(sorted(g)) for g in group_anagrams([''])) == [('',)]
assert sorted(tuple(sorted(g)) for g in group_anagrams(['a'])) == [('a',)]
print('TESTS_OK')
