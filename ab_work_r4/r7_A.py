def eval_rpn(tokens):
    stack = []
    for tok in tokens:
        if tok in ("+", "-", "*", "/"):
            b = stack.pop()
            a = stack.pop()
            if tok == "+":
                stack.append(a + b)
            elif tok == "-":
                stack.append(a - b)
            elif tok == "*":
                stack.append(a * b)
            else:  # "/"
                q = abs(a) // abs(b)
                if (a < 0) != (b < 0):
                    q = -q
                stack.append(q)
        else:
            stack.append(int(tok))
    return stack[0]


assert eval_rpn(['2','1','+','3','*']) == 9
assert eval_rpn(['4','13','5','/','+']) == 6
assert eval_rpn(['10','6','9','3','+','-11','*','/','*','17','+','5','+']) == 22
print('TESTS_OK')
