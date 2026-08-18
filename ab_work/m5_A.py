def word_count(text):
    counts = {}
    for word in text.split():
        counts[word] = counts.get(word, 0) + 1
    return counts


assert word_count('a b a') == {'a': 2, 'b': 1}
assert word_count('') == {}
assert word_count('x') == {'x': 1}
print('TESTS_OK')
