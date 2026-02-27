import urllib.request, json
try:
    data = json.dumps({'username': 'student1', 'password': 'student1password'}).encode('utf-8')
    req1 = urllib.request.Request('http://localhost:8000/api/token/', data=data, headers={'Content-Type': 'application/json'})
    res1 = urllib.request.urlopen(req1)
    token = json.loads(res1.read().decode('utf-8'))['access']

    req2 = urllib.request.Request('http://localhost:8000/api/tasks/', headers={'Authorization': 'Bearer ' + token})
    res2 = urllib.request.urlopen(req2)
    tasks = json.loads(res2.read().decode('utf-8'))
    task_id = tasks[0]['id']

    submit_data = json.dumps({'code': 'print("Hello, World!")', 'language': 'Python', 'run_results': [{'passed': True}]}).encode('utf-8')
    req3 = urllib.request.Request('http://localhost:8000/api/tasks/' + str(task_id) + '/submit/', data=submit_data, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    res3 = urllib.request.urlopen(req3)
    print(res3.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTP ERROR:', e.code)
    print(e.read().decode('utf-8'))
except Exception as e:
    print('ERROR:', str(e))
