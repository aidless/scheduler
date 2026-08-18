def fizzbuzz(n):
    result = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            result.append('FizzBuzz')
        elif i % 3 == 0:
            result.append('Fizz')
        elif i % 5 == 0:
            result.append('Buzz')
        else:
            result.append(str(i))
    return result


assert fizzbuzz(15)[14] == 'FizzBuzz'
assert fizzbuzz(15)[2] == 'Fizz'
assert fizzbuzz(15)[4] == 'Buzz'
assert fizzbuzz(15)[0] == '1'
assert len(fizzbuzz(7)) == 7
print('TESTS_OK')
