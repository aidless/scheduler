from collections import deque

def course_schedule(num_courses, prerequisites):
    graph = [[] for _ in range(num_courses)]
    indegree = [0] * num_courses
    for a, b in prerequisites:
        graph[b].append(a)
        indegree[a] += 1
    queue = deque([i for i in range(num_courses) if indegree[i] == 0])
    completed = 0
    while queue:
        course = queue.popleft()
        completed += 1
        for nxt in graph[course]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return completed == num_courses


assert course_schedule(2, [[1,0]]) is True
assert course_schedule(2, [[1,0],[0,1]]) is False
assert course_schedule(1, []) is True
assert course_schedule(3, [[1,0],[1,2],[0,1]]) is False
print('TESTS_OK')
