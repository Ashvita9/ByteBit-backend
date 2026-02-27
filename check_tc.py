import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from arena_api.models import CodingTask

for t in CodingTask.objects(title__icontains='Hello'):
    print('Task:', t.title)
    for tc in t.test_cases:
        print(f' TC: expected={repr(tc.output_data)}, hidden={tc.is_hidden}')
