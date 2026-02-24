import urllib.request, json, urllib.error

url = 'http://localhost:8000/api/tasks/'
data = json.dumps({
    'title': 'Debug Task',
    'description': 'Testing',
    'difficulty': 'Easy',
    'test_cases': [],
    'time_limit': 300
}).encode('utf-8')

req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(f"Error {e.code}:")
    print(e.read().decode('utf-8'))
