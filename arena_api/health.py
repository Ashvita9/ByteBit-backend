import os
import django
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    """
    GET /api/health/
    Returns server status, dependency connectivity, and a full list of API endpoints.
    No authentication required — use this to verify your backend is alive.
    """
    checks = {
        'django': {'status': 'ok', 'version': django.get_version()},
        'mongodb': {'status': 'unknown'},
        'redis': {'status': 'unknown'},
    }

    # ── Check MongoDB ──
    try:
        from mongoengine import get_db
        db = get_db()
        db.command('ping')
        checks['mongodb'] = {'status': 'ok', 'database': db.name}
    except Exception as e:
        checks['mongodb'] = {'status': 'error', 'detail': str(e)}

    # ── Check Redis ──
    try:
        redis_url = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/1')
        import redis as redis_lib
        r = redis_lib.from_url(redis_url, socket_connect_timeout=3)
        r.ping()
        checks['redis'] = {'status': 'ok'}
    except ImportError:
        checks['redis'] = {'status': 'skipped', 'detail': 'redis package not installed'}
    except Exception as e:
        checks['redis'] = {'status': 'error', 'detail': str(e)}

    # ── Overall status ──
    # Consider healthy if at least Django + MongoDB are ok (Redis is optional)
    critical_ok = checks['django']['status'] == 'ok' and checks['mongodb']['status'] == 'ok'
    all_ok = all(c['status'] == 'ok' for c in checks.values())

    # ── API Endpoint Directory ──
    endpoints = [
        # Health
        {'method': 'GET',             'path': '/api/health/',                         'desc': 'Health check + API directory',       'auth': 'None'},

        # Auth (no login needed)
        {'method': 'POST',            'path': '/api/auth/register/',                  'desc': 'Register a new user',                'auth': 'None'},
        {'method': 'POST',            'path': '/api/auth/login/',                     'desc': 'Login → JWT access + refresh token', 'auth': 'None'},
        {'method': 'POST',            'path': '/api/auth/teacher/create/',            'desc': 'Create a teacher account',            'auth': 'Admin'},

        # Profile
        {'method': 'GET',             'path': '/api/me/',                             'desc': 'Get your profile (XP, rank, etc.)',  'auth': 'User'},

        # Classrooms
        {'method': 'GET | POST',      'path': '/api/classrooms/',                     'desc': 'List / create classrooms',            'auth': 'Teacher'},
        {'method': 'GET',             'path': '/api/classrooms/my/',                  'desc': 'My enrolled / owned classrooms',      'auth': 'User'},
        {'method': 'POST',            'path': '/api/classrooms/join/',                'desc': 'Join classroom by code',              'auth': 'User'},
        {'method': 'GET|PATCH|DELETE', 'path': '/api/classrooms/<id>/',               'desc': 'Classroom detail / update / delete',  'auth': 'User/Teacher'},
        {'method': 'POST',            'path': '/api/classrooms/<id>/join-public/',    'desc': 'Auto-join a public classroom',        'auth': 'User'},
        {'method': 'POST',            'path': '/api/classrooms/<id>/students/',       'desc': 'Add student by username',             'auth': 'Teacher'},
        {'method': 'DELETE',          'path': '/api/classrooms/<id>/students/<sid>/', 'desc': 'Remove student from classroom',       'auth': 'Teacher'},
        {'method': 'POST',            'path': '/api/classrooms/<id>/announcements/',  'desc': 'Post an announcement',               'auth': 'Teacher'},
        {'method': 'GET | POST',      'path': '/api/classrooms/<id>/tickets/',        'desc': 'List / raise tickets',                'auth': 'Teacher'},

        # Battle
        {'method': 'POST',            'path': '/api/battle/scout/',                   'desc': 'Scout a random battle match',         'auth': 'None'},

        # Tasks & Submissions
        {'method': 'GET',             'path': '/api/tasks/<id>/submissions/',         'desc': 'View task submissions',               'auth': 'Teacher'},
        {'method': 'POST',            'path': '/api/tasks/<id>/run/',                 'desc': 'Run code against test cases',         'auth': 'User'},
        {'method': 'POST',            'path': '/api/tasks/<id>/submit/',              'desc': 'Submit code for grading',             'auth': 'User'},
        {'method': 'POST',            'path': '/api/tasks/<id>/unsubmit/',            'desc': 'Unsubmit active submission',          'auth': 'User'},

        # Admin
        {'method': 'GET',             'path': '/api/admin/users/',                    'desc': 'List all users',                      'auth': 'Admin'},
        {'method': 'DELETE | PATCH',  'path': '/api/admin/users/<id>/',               'desc': 'Delete / update user',                'auth': 'Admin'},
        {'method': 'GET',             'path': '/api/admin/classrooms/',               'desc': 'List all classrooms',                 'auth': 'Admin'},
        {'method': 'DELETE',          'path': '/api/admin/classrooms/<id>/',          'desc': 'Delete a classroom',                  'auth': 'Admin'},
        {'method': 'GET',             'path': '/api/admin/tickets/',                  'desc': 'List all tickets',                    'auth': 'Admin'},
        {'method': 'PATCH',           'path': '/api/admin/tickets/<id>/',             'desc': 'Update ticket status',                'auth': 'Admin'},
        {'method': 'GET',             'path': '/api/admin/logs/',                     'desc': 'View action logs',                    'auth': 'Admin'},

        # Teacher ticket
        {'method': 'POST',            'path': '/api/tickets/raise/',                  'desc': 'Teacher raises a ticket',             'auth': 'User'},
    ]

    if all_ok:
        overall = 'healthy'
    elif critical_ok:
        overall = 'healthy (redis unavailable)'
    else:
        overall = 'unhealthy'

    resp_status = 200 if critical_ok else 503
    return Response({
        'status': overall,
        'checks': checks,
        'total_endpoints': len(endpoints),
        'endpoints': endpoints,
    }, status=resp_status)
