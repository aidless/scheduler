def group_anagrams(strs):
    anagrams = {}
    for s in strs:
        key = "".join(sorted(s))
        if key not in anagrams:
            anagrams[key] = []
        anagrams[key].append(s)
    return list(anagrams.values())


assert sorted(tuple(sorted(g)) for g in group_anagrams(['eat','tea','tan','ate','nat','bat'])) == [('ate','eat','tea'),('bat',),('nat','tan')]
assert sorted(tuple(sorted(g)) for g in group_anagrams([''])) == [('',)]
assert sorted(tuple(sorted(g)) for g in group_anagrams(['a'])) == [('a',)]
print('TESTS_OK')
