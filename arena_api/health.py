from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.decorators import api_view, permission_classes, renderer_classes
from rest_framework import permissions
from rest_framework.response import Response
import django
import os

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@renderer_classes([TemplateHTMLRenderer, JSONRenderer])
def health_check(request):
    """
    GET /api/health/
    Returns server status, dependency connectivity, and a full list of API endpoints.
    Can be viewed in browser for a premium status dashboard.
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

    # ── API Endpoint Directory ──
    endpoints = [
        {'method': 'GET', 'path': '/api/health/', 'desc': 'Health check + API directory', 'auth': 'None'},
        {'method': 'POST', 'path': '/api/auth/register/', 'desc': 'Register a new user', 'auth': 'None'},
        {'method': 'POST', 'path': '/api/auth/login/', 'desc': 'Login → JWT tokens', 'auth': 'None'},
        {'method': 'GET', 'path': '/api/me/', 'desc': 'Get your profile', 'auth': 'User'},
        {'method': 'GET | POST', 'path': '/api/classrooms/', 'desc': 'List / create classrooms', 'auth': 'Teacher'},
        {'method': 'POST', 'path': '/api/battle/scout/', 'desc': 'Scout a battle match', 'auth': 'None'},
        {'method': 'POST', 'path': '/api/tasks/<id>/run/', 'desc': 'Run code', 'auth': 'User'},
        {'method': 'POST', 'path': '/api/tasks/<id>/submit/', 'desc': 'Submit code', 'auth': 'User'},
    ]

    # ── Overall status ──
    critical_ok = checks['django']['status'] == 'ok' and checks['mongodb']['status'] == 'ok'
    all_ok = all(c['status'] == 'ok' for c in checks.values())

    if all_ok:
        overall = 'healthy'
    elif critical_ok:
        overall = 'healthy (redis unavailable)'
    else:
        overall = 'unhealthy'

    data = {
        'status': overall,
        'checks': checks,
        'total_endpoints': len(endpoints),
        'endpoints': endpoints,
    }

    if request.accepted_renderer.format == 'html':
        return Response(data, template_name='health.html')
    
    return Response(data, status=200 if critical_ok else 503)
