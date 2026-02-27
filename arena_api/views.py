import random
import string
from datetime import datetime

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_mongoengine import viewsets
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from django.contrib.auth.models import User

from .models import (
    CodingTask, CoderProfile, BattleRoom,
    Submission, Classroom, Announcement, Ticket, ActionLog,
    GlobalAnnouncement
)
from .serializers import (
    CodingTaskSerializer,
    CoderProfileSerializer,
    UserRegistrationSerializer,
)
from rest_framework.exceptions import AuthenticationFailed


# â”€â”€ Permissions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class IsTeacherOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user and not request.user.is_active:
            return False
            
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class IsTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user and not request.user.is_active:
            return False
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


# â”€â”€ Task ViewSet â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class CodingTaskViewSet(viewsets.ModelViewSet):
    lookup_field    = 'id'
    queryset        = CodingTask.objects.all()
    serializer_class = CodingTaskSerializer
    permission_classes = [IsTeacherOrReadOnly]

    def get_queryset(self):
        qs = CodingTask.objects.all()
        difficulty = self.request.query_params.get('difficulty')
        tech_stack = self.request.query_params.get('tech_stack')
        classroom_id = self.request.query_params.get('classroom_id')
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        if tech_stack:
            qs = qs.filter(tech_stack=tech_stack)
        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)
        return qs

    def perform_create(self, serializer):
        task = serializer.save()
        # Auto-link task into the classroom's task_ids list
        classroom_id = self.request.data.get('classroom_id')
        if classroom_id:
            try:
                c = Classroom.objects.get(id=classroom_id)
                if str(task.id) not in c.task_ids:
                    c.task_ids.append(str(task.id))
                    c.save()
            except Exception:
                pass



# â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class UserRegistrationView(generics.CreateAPIView):
    serializer_class   = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def create_teacher(request):
    username = request.data.get('username')
    email = request.data.get('email', '')

    if not username:
        return Response({'error': 'Username is required'}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username=username).exists():
        return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)

    password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    user = User.objects.create_user(username=username, email=email, password=password)
    user.is_staff = True
    user.save()
    CoderProfile(user_id=str(user.id), role='TEACHER').save()

    return Response({
        'message': 'Teacher created successfully',
        'username': username,
        'password': password
    }, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        if not self.user.is_active:
            raise AuthenticationFailed('This account has been locked by an administrator.')
            
        data['username'] = self.user.username
        data['user_id']  = str(self.user.id)

        # Base role on user flags first
        if self.user.is_superuser:
            data['role'] = 'ADMIN'
            return data
        
        # If they are staff, they are a Teacher
        is_teacher = getattr(self.user, 'is_staff', False)

        try:
            profile      = CoderProfile.objects.get(user_id=str(self.user.id))
            data['role'] = profile.role
            data['xp']   = profile.xp
            data['level']  = profile.level
            data['wins']   = profile.wins
            data['losses'] = profile.losses
            data['rank']   = profile.rank
            data['badges'] = profile.badges
        except Exception:
            data['role'] = 'STUDENT'
        return data


class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# â”€â”€ Profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def my_profile(request):
    try:
        profile = CoderProfile.objects.get(user_id=str(request.user.id))
        data = CoderProfileSerializer(profile).data
        data['username'] = request.user.username
        return Response(data)
    except CoderProfile.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=404)


# â”€â”€ Classroom â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _classroom_data(c, include_students=False):
    """Serialize a Classroom document to a dict."""
    d = {
        'id': str(c.id),
        'name': c.name,
        'code': c.code,
        'type': c.type,
        'teacher_id': c.teacher_id,
        'student_count': len(c.student_ids),
        'student_ids': list(c.student_ids),   # â† exposed so frontend can diff enrolled vs public
        'task_ids': c.task_ids,
        'is_locked': c.is_locked,
        'created_at': c.created_at.isoformat() if c.created_at else None,
    }
    if include_students:
        students = []
        for uid in c.student_ids:
            try:
                u = User.objects.get(id=uid)
                students.append({'id': uid, 'username': u.username})
            except Exception:
                students.append({'id': uid, 'username': '???'})
        d['students'] = students
    return d



@api_view(['GET', 'POST'])
@permission_classes([IsTeacher])
def classrooms(request):
    """
    GET  /api/classrooms/      â€” list classrooms owned by this teacher
    POST /api/classrooms/      â€” create a new classroom
    """
    if request.method == 'GET':
        cs = Classroom.objects.filter(teacher_id=str(request.user.id))
        return Response([_classroom_data(c) for c in cs])

    # POST â€” create
    name = request.data.get('name', '').strip()
    ctype = request.data.get('type', 'Public')
    if not name:
        return Response({'error': 'name is required'}, status=400)

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    c = Classroom(name=name, type=ctype, teacher_id=str(request.user.id), code=code)
    c.save()
    return Response(_classroom_data(c), status=201)


@api_view(['GET', 'DELETE', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def classroom_detail(request, classroom_id):
    """
    GET    /api/classrooms/<id>/  â€” get detail (students, announcements, tasks)
    PATCH  /api/classrooms/<id>/  â€” update name/type/is_locked (teacher only)
    DELETE /api/classrooms/<id>/  â€” delete classroom (teacher only)
    """
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)

    if request.method == 'GET':
        d = _classroom_data(c, include_students=True)
        d['announcements'] = [
            {'message': a.message, 'created_at': a.created_at.isoformat(), 'pinned': a.pinned}
            for a in c.announcements
        ]
        # Fetch associated tasks
        tasks = []
        for tid in c.task_ids:
            try:
                t = CodingTask.objects.get(id=tid)
                tasks.append({
                    'id': str(t.id),
                    'title': t.title,
                    'difficulty': t.difficulty,
                    'tech_stack': t.tech_stack,
                    'task_type': t.task_type,
                    'due_date': t.due_date.isoformat() if t.due_date else None,
                    'submissions_count': len(t.submissions),
                })
            except Exception:
                pass
        d['tasks'] = tasks
        return Response(d)

    if request.method == 'PATCH':
        if str(c.teacher_id) != str(request.user.id):
            return Response({'error': 'Forbidden'}, status=403)
        if 'name' in request.data:
            c.name = request.data['name']
        if 'type' in request.data:
            c.type = request.data['type']
        if 'is_locked' in request.data:
            c.is_locked = request.data['is_locked']
        c.save()
        return Response(_classroom_data(c))

    if request.method == 'DELETE':
        if str(c.teacher_id) != str(request.user.id):
            return Response({'error': 'Forbidden'}, status=403)
        c.delete()
        return Response(status=204)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def join_classroom(request):
    """
    POST /api/classrooms/join/
    Body: { "code": "ABC123" }
    Student joins a classroom by code.
    """
    code = request.data.get('code', '').strip().upper()
    if not code:
        return Response({'error': 'code is required'}, status=400)

    try:
        c = Classroom.objects.get(code=code)
    except Exception:
        return Response({'error': 'Invalid classroom code'}, status=404)

    if c.is_locked:
        return Response({'error': 'This classroom is locked'}, status=403)

    uid = str(request.user.id)
    if uid not in c.student_ids:
        c.student_ids.append(uid)
        c.save()

    return Response(_classroom_data(c))


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def my_classrooms(request):
    """
    GET /api/classrooms/my/
    Students: returns enrolled classrooms + all public unlocked classrooms.
    Teachers/Admins: returns classrooms they own.
    """
    uid = str(request.user.id)
    profile = CoderProfile.objects.filter(user_id=uid).first()
    role = profile.role if profile else 'STUDENT'

    if role in ('TEACHER', 'ADMIN') or request.user.is_staff:
        cs = Classroom.objects.filter(teacher_id=uid)
        return Response([_classroom_data(c) for c in cs])

    # Student: enrolled private classrooms + all public ones
    enrolled    = list(Classroom.objects.filter(student_ids=uid))
    enrolled_ids = {str(c.id) for c in enrolled}
    public_all  = [c for c in Classroom.objects.filter(type='Public', is_locked=False)
                   if str(c.id) not in enrolled_ids]

    # Auto-enroll in public classrooms they open (handled separately), just surface them
    result = enrolled + public_all
    return Response([_classroom_data(c) for c in result])


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def join_public_classroom(request, classroom_id):
    """
    POST /api/classrooms/<id>/join-public/
    Auto-joins a public classroom without a code.
    """
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)

    if c.type != 'Public':
        return Response({'error': 'This classroom requires a code to join'}, status=403)
    if c.is_locked:
        return Response({'error': 'This classroom is locked'}, status=403)

    uid = str(request.user.id)
    if uid not in c.student_ids:
        c.student_ids.append(uid)
        c.save()
    return Response(_classroom_data(c))


@api_view(['DELETE'])
@permission_classes([IsTeacher])
def remove_student(request, classroom_id, student_id):
    """DELETE /api/classrooms/<id>/students/<student_id>/"""
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)

    if str(c.teacher_id) != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    sid = str(student_id)
    if sid in c.student_ids:
        c.student_ids.remove(sid)
        c.save()
    return Response({'status': 'removed'})


@api_view(['POST'])
@permission_classes([IsTeacher])
def add_student_by_username(request, classroom_id):
    """
    POST /api/classrooms/<id>/students/
    Body: { "username": "..." }
    """
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)

    if str(c.teacher_id) != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    username = request.data.get('username', '').strip()
    try:
        u = User.objects.get(username=username)
    except User.DoesNotExist:
        return Response({'error': f'User "{username}" not found'}, status=404)

    if str(u.id) not in c.student_ids:
        c.student_ids.append(str(u.id))
        c.save()
    return Response({'status': 'added', 'username': u.username, 'user_id': str(u.id)})


# â”€â”€ Announcements â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@api_view(['POST'])
@permission_classes([IsTeacher])
def post_announcement(request, classroom_id):
    """POST /api/classrooms/<id>/announcements/"""
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)

    if str(c.teacher_id) != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    message = request.data.get('message', '').strip()
    if not message:
        return Response({'error': 'message is required'}, status=400)

    pinned = request.data.get('pinned', False)
    ann = Announcement(message=message, pinned=pinned)
    c.announcements.insert(0, ann)
    c.save()
    return Response({'status': 'posted'}, status=201)


# â”€â”€ Tickets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@api_view(['GET', 'POST'])
@permission_classes([IsTeacher])
def tickets(request, classroom_id):
    """
    GET  /api/classrooms/<id>/tickets/  â€” list tickets for this classroom
    POST /api/classrooms/<id>/tickets/  â€” raise a ticket
    """
    if request.method == 'GET':
        ts = Ticket.objects.filter(classroom_id=classroom_id)
        return Response([{
            'id': str(t.id),
            'student_id': t.student_id,
            'task_id': t.task_id,
            'reason': t.reason,
            'status': t.status,
            'created_at': t.created_at.isoformat(),
        } for t in ts])

    # POST
    student_id = request.data.get('student_id')
    task_id    = request.data.get('task_id')
    reason     = request.data.get('reason', '').strip()

    if not all([student_id, task_id, reason]):
        return Response({'error': 'student_id, task_id, and reason are required'}, status=400)

    t = Ticket(
        raised_by_id=str(request.user.id),
        student_id=str(student_id),
        task_id=task_id,
        classroom_id=classroom_id,
        reason=reason,
    )
    t.save()
    return Response({'status': 'raised', 'ticket_id': str(t.id)}, status=201)


# â”€â”€ Submissions (Teacher view) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@api_view(['GET'])
@permission_classes([IsTeacher])
def task_submissions(request, task_id):
    """Return only ACTIVE (latest) submissions per student â€” teacher only."""
    try:
        task = CodingTask.objects.get(id=task_id)
    except Exception:
        return Response({'error': 'Task not found'}, status=404)

    from .serializers import SubmissionSerializer
    # Only latest (active) submission per student
    active = [s for s in (task.submissions or []) if getattr(s, 'is_active', True)]
    return Response(SubmissionSerializer(active, many=True).data)


# â”€â”€ Battle Matchmaking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _generate_room_code(length=6):
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=length))
        if not BattleRoom.objects(room_code=code).first():
            return code


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def scout_match(request):
    difficulty = request.data.get('difficulty')
    tech_stack = request.data.get('tech_stack')

    qs = CodingTask.objects.all()
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    if tech_stack:
        qs = qs.filter(tech_stack=tech_stack)

    count = qs.count()
    if count == 0:
        qs = CodingTask.objects.all()
        count = qs.count()
        if count == 0:
            return Response({'error': 'No tasks available'}, status=404)

    task = qs[random.randint(0, count - 1)]
    room_code = _generate_room_code()
    room = BattleRoom(room_code=room_code, task_id=str(task.id))
    if request.user.is_authenticated:
        room.player1_id = str(request.user.id)
    room.save()

    return Response({
        'room_id':    f'battle_{task.id}',
        'room_code':  room_code,
        'task_id':    str(task.id),
        'task_title': task.title,
    })


# â”€â”€ Run Code (test without saving) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def run_code(request, task_id):
    """
    POST /api/tasks/<id>/run/
    Body: { "code": "...", "language": "Python" }
    Executes code against the task's test cases. Does NOT save a submission.
    """
    try:
        task = CodingTask.objects.get(id=task_id)
    except Exception:
        return Response({'error': 'Task not found'}, status=404)

    code     = request.data.get('code', '')
    language = request.data.get('language', task.tech_stack or 'Python')

    test_cases = [
        {'input_data': tc.input_data, 'output_data': tc.output_data, 'is_hidden': tc.is_hidden}
        for tc in (task.test_cases or [])
    ]

    if not test_cases:
        return Response({'error': 'No test cases defined for this task'}, status=400)

    from .runner import run_test_cases
    result = run_test_cases(code, language, test_cases)

    visible = [r for r in result['results'] if not r.get('is_hidden', False)]
    return Response({
        'all_passed':   result['all_passed'],
        'results':      visible,
        'total':        len(result['results']),
        'passed_count': sum(1 for r in result['results'] if r['passed']),
    })


# â”€â”€ Record Submission (versioned) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def record_submission(request, task_id):
    """
    POST /api/tasks/<id>/submit/
    Body: { "code": "...", "language": "Python", "run_results": [...] }
    Deactivates previous submission from this user, saves new active one.
    """
    try:
        task = CodingTask.objects.get(id=task_id)
    except Exception:
        return Response({'error': 'Task not found'}, status=404)

    username    = request.user.username
    user_id     = str(request.user.id)
    code        = request.data.get('code', '')
    language    = request.data.get('language', task.tech_stack or 'Python')
    run_results = request.data.get('run_results', [])

    all_passed = all(r.get('passed', False) for r in run_results) if run_results else False
    total      = max(len(run_results), 1)
    n_passed   = sum(1 for r in run_results if r.get('passed', False))
    score      = round(n_passed / total * 100, 1)   # percentage

    # â”€â”€ Grading config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    grading_mode  = getattr(task, 'grading_mode', 'Percentage') or 'Percentage'
    max_marks     = float(getattr(task, 'max_marks', 100) or 100)
    marks_obtained = round(score / 100 * max_marks, 1)
    grade          = task.compute_grade(score) if hasattr(task, 'compute_grade') else ''
    is_final = getattr(task, 'is_final', False)
    passed = True if is_final else all_passed
    remarks = f'Final assessment submitted. Score: {score}%' if is_final else ('All test cases passed.' if all_passed else f'{n_passed}/{total} test cases passed.')

    now = datetime.utcnow()

    if task.submissions is None:
        task.submissions = []

    # Deactivate all prior active submissions from this user on this task
    for s in task.submissions:
        if s.user_id == user_id and getattr(s, 'is_active', True):
            s.is_active = False
            s.status    = 'Unsubmitted'

    new_sub = Submission(
        user_id        = user_id,
        username       = username,
        code           = code,
        passed         = passed,
        output         = '',
        language       = language,
        score          = score,
        marks_obtained = marks_obtained,
        grade          = grade,
        remarks        = remarks,
        is_active      = True,
        status         = 'Submitted',
        last_edited_at = now,
        created_at     = now,
    )
    task.submissions.append(new_sub)
    task.save()

    # â”€â”€ Award XP to STUDENT profiles only â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    xp_earned = 0
    try:
        prof = CoderProfile.objects.get(user_id=user_id)
        if prof.role == 'STUDENT':
            already_passed = any(
                getattr(s, 'passed', False) and not getattr(s, 'is_active', True)
                for s in task.submissions[:-1]
            )
            if not already_passed:
                xp_earned = int(score)
                prof.xp += xp_earned
                prof.recalc_rank()
                prof.save()
    except Exception:
        pass

    # â”€â”€ Action Log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        classroom_name = ''
        if task.classroom_id:
            try:
                cr = Classroom.objects.get(id=task.classroom_id)
                classroom_name = cr.name
            except Exception:
                pass
        ActionLog(
            action_type    = 'submission',
            actor_id       = user_id,
            actor_username = username,
            task_id        = str(task.id),
            task_title     = task.title,
            classroom_id   = task.classroom_id or '',
            classroom_name = classroom_name,
            details        = f'Score: {score}% ({marks_obtained}/{max_marks} marks). {"Passed" if all_passed else "Failed"}.',
        ).save()
    except Exception:
        pass

    return Response({
        'status': 'recorded',
        'score': score,
        'marks_obtained': marks_obtained,
        'max_marks': max_marks,
        'grading_mode': grading_mode,
        'grade': grade,
        'remarks': remarks,
        'passed': all_passed,
        'xp_earned': xp_earned,
    })

# â”€â”€ Unsubmit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def unsubmit(request, task_id):
    """POST /api/tasks/<id>/unsubmit/ â€” marks active submission as Unsubmitted."""
    try:
        task = CodingTask.objects.get(id=task_id)
    except Exception:
        return Response({'error': 'Task not found'}, status=404)

    uid     = str(request.user.id)
    changed = False
    for s in (task.submissions or []):
        if s.user_id == uid and getattr(s, 'is_active', True):
            s.status = 'Unsubmitted'
            changed  = True
    if changed:
        task.save()
        return Response({'status': 'unsubmitted'})
    return Response({'error': 'No active submission found'}, status=404)


# ── Helper: log an action ────────────────────────────────────────────────────

def _log(action_type, actor, target_user=None, task=None, classroom=None, details=''):
    try:
        try:
            tu = User.objects.get(id=target_user) if target_user else None
        except Exception:
            tu = None
        ActionLog(
            action_type     = action_type,
            actor_id        = str(actor.id),
            actor_username  = actor.username,
            target_user_id  = str(tu.id) if tu else None,
            target_username = tu.username if tu else '',
            task_id         = str(task.id) if task else '',
            task_title      = task.title if task else '',
            classroom_id    = str(classroom.id) if classroom else '',
            classroom_name  = classroom.name if classroom else '',
            details         = details,
        ).save()
    except Exception:
        pass


def _is_admin(request):
    return request.user.is_superuser or (
        CoderProfile.objects.filter(user_id=str(request.user.id), role='ADMIN').exists()
    )


# ── TEACHER: Raise a ticket ──────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def raise_ticket(request):
    data = request.data
    ticket_type  = data.get('ticket_type', 'Revoke Credit')
    student_id   = data.get('student_id')
    task_id      = data.get('task_id', '')
    classroom_id = data.get('classroom_id', '')
    reason       = data.get('reason', '').strip()

    if not student_id or not classroom_id or not reason:
        return Response({'error': 'student_id, classroom_id, and reason are required'}, status=400)

    try:
        student = User.objects.get(id=student_id)
        student_username = student.username
    except Exception:
        return Response({'error': 'Student not found'}, status=404)

    task_title = ''
    classroom_name = ''
    try:
        cr = Classroom.objects.get(id=classroom_id)
        classroom_name = cr.name
    except Exception:
        pass
    if task_id:
        try:
            t = CodingTask.objects.get(id=task_id)
            task_title = t.title
        except Exception:
            pass

    ticket = Ticket(
        ticket_type        = ticket_type,
        raised_by_id       = str(request.user.id),
        raised_by_username = request.user.username,
        student_id         = str(student_id),
        student_username   = student_username,
        task_id            = task_id,
        task_title         = task_title,
        classroom_id       = classroom_id,
        classroom_name     = classroom_name,
        reason             = reason,
    )
    ticket.save()
    _log('ticket_raised', request.user, target_user=str(student_id), details=f'Type: {ticket_type}. Reason: {reason}')
    return Response({'status': 'raised', 'ticket_id': str(ticket.id)}, status=201)


# ── ADMIN: Users ─────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_users(request):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    role_filter = request.query_params.get('role')
    result = []
    for u in User.objects.all().order_by('id'):
        prof = CoderProfile.objects.filter(user_id=str(u.id)).first()
        role = prof.role if prof else ('ADMIN' if u.is_superuser else 'STUDENT')
        if role_filter and role != role_filter:
            continue
        row = {
            'id': str(u.id), 'username': u.username, 'email': u.email,
            'role': role, 'is_active': u.is_active,
            'date_joined': u.date_joined.isoformat(),
            'xp': (prof.xp if prof and role == 'STUDENT' else None),
            'rank': (prof.rank if prof and role == 'STUDENT' else None),
        }
        result.append(row)
    return Response(result)


@api_view(['DELETE', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def admin_user_action(request, user_id):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    try:
        u = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
    if request.method == 'DELETE':
        _log('user_deleted', request.user, target_user=user_id, details=f'User {u.username} deleted.')
        u.delete()
        CoderProfile.objects.filter(user_id=str(user_id)).delete()
        return Response({'status': 'deleted'})
    if request.method == 'PATCH':
        action = request.data.get('action')
        new_role = request.data.get('role')

        if action == 'reset_password':
            new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            u.set_password(new_password)
            u.save()
            _log('password_reset', request.user, target_user=user_id, details=f'Password reset for {u.username}.')
            return Response({'status': 'ok', 'password': new_password})
            
        elif new_role in ['ADMIN', 'TEACHER', 'STUDENT']:
            # For superusers (ADMIN role)
            if new_role == 'ADMIN':
                u.is_superuser = True
                u.save()
            else:
                u.is_superuser = False
                u.save()
            
            # Update CoderProfile role
            prof = CoderProfile.objects.filter(user_id=str(user_id)).first()
            if not prof:
                prof = CoderProfile(user_id=str(user_id))
            
            prof.role = new_role
            if new_role != 'STUDENT' and prof.rank != 'Not Applicable':
                prof.rank = 'Not Applicable'
            prof.save()
            
            _log('role_changed', request.user, target_user=user_id, details=f'Role changed to {new_role} for {u.username}.')
            return Response({'status': 'ok', 'role': new_role})
            
        else:
            u.is_active = not u.is_active
            u.save()
            _log('user_locked' if not u.is_active else 'user_unlocked', request.user, target_user=user_id, details=f'{u.username} {"locked" if not u.is_active else "unlocked"}.')
            return Response({'status': 'ok', 'is_active': u.is_active})


# ── ADMIN: Classrooms ────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_classrooms(request):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    result = []
    for c in Classroom.objects.all():
        try:
            teacher = User.objects.get(id=c.teacher_id).username
        except Exception:
            teacher = '???'
        d = _classroom_data(c)
        d['teacher_name'] = teacher
        result.append(d)
    return Response(result)


@api_view(['PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def admin_classroom_action(request, classroom_id):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Not found'}, status=404)
    if request.method == 'DELETE':
        _log('classroom_deleted', request.user, classroom=c, details=f'Classroom "{c.name}" deleted.')
        c.delete()
        return Response({'status': 'deleted'})
    if 'is_locked' in request.data:
        c.is_locked = bool(request.data['is_locked'])
        c.save()
        _log('classroom_locked' if c.is_locked else 'classroom_unlocked', request.user, classroom=c, details=f'"{c.name}" {"locked" if c.is_locked else "unlocked"}.')
    return Response(_classroom_data(c))


# ── ADMIN: Tickets ───────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_tickets(request):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    status_f = request.query_params.get('status')
    qs = Ticket.objects.all()
    if status_f:
        qs = qs.filter(status=status_f)
    result = []
    for t in qs:
        result.append({
            'id': str(t.id), 'ticket_type': t.ticket_type,
            'raised_by': t.raised_by_username, 'student': t.student_username,
            'student_id': t.student_id, 'task_id': t.task_id,
            'task_title': t.task_title, 'classroom_id': t.classroom_id,
            'classroom_name': t.classroom_name, 'reason': t.reason,
            'status': t.status, 'admin_note': t.admin_note,
            'created_at': t.created_at.isoformat(),
            'resolved_at': t.resolved_at.isoformat() if t.resolved_at else None,
        })
    return Response(result)


@api_view(['PATCH'])
@permission_classes([permissions.IsAuthenticated])
def admin_ticket_action(request, ticket_id):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    try:
        t = Ticket.objects.get(id=ticket_id)
    except Exception:
        return Response({'error': 'Ticket not found'}, status=404)

    action     = request.data.get('action', 'dismiss')
    admin_note = request.data.get('admin_note', '').strip()
    now        = datetime.utcnow()
    result_detail = ''

    if action == 'revoke_credit' and t.task_id:
        try:
            task = CodingTask.objects.get(id=t.task_id)
            for s in (task.submissions or []):
                if s.user_id == t.student_id and getattr(s, 'is_active', True):
                    s.is_active = False
                    s.status = 'Unsubmitted'
                    s.score = 0.0
                    try: s.marks_obtained = 0.0
                    except: pass
                    s.remarks = 'Credits revoked by admin via ticket.'
            task.save()
            result_detail = f'Credits revoked for {t.student_username} on "{t.task_title}".'
        except Exception as e:
            result_detail = f'Could not revoke: {e}'
        try:
            prof = CoderProfile.objects.get(user_id=t.student_id)
            prof.xp = max(0, prof.xp - 50)
            prof.recalc_rank()
            prof.save()
        except Exception:
            pass

    elif action == 'remove_student':
        try:
            cr = Classroom.objects.get(id=t.classroom_id)
            if t.student_id in cr.student_ids:
                cr.student_ids.remove(t.student_id)
                cr.save()
            result_detail = f'{t.student_username} removed from "{t.classroom_name}".'
        except Exception as e:
            result_detail = f'Could not remove: {e}'

    else:
        result_detail = 'Ticket dismissed without action.'

    t.status      = 'Resolved'
    t.admin_note  = admin_note or result_detail
    t.resolved_at = now
    t.save()

    try:
        cr = Classroom.objects.get(id=t.classroom_id)
    except Exception:
        cr = None
    _log(f'ticket_{action}', request.user, target_user=t.student_id, classroom=cr, details=result_detail)

    return Response({'status': 'resolved', 'detail': result_detail})


# ── ADMIN: Action Logs ───────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_logs(request):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    qs = ActionLog.objects.all()
    if request.query_params.get('classroom_id'):
        qs = qs.filter(classroom_id=request.query_params['classroom_id'])
    if request.query_params.get('task_id'):
        qs = qs.filter(task_id=request.query_params['task_id'])
    if request.query_params.get('student'):
        qs = qs.filter(target_username__icontains=request.query_params['student'])
    if request.query_params.get('action_type'):
        qs = qs.filter(action_type=request.query_params['action_type'])
    if request.query_params.get('date_from'):
        try:
            qs = qs.filter(created_at__gte=datetime.fromisoformat(request.query_params['date_from']))
        except Exception: pass
    if request.query_params.get('date_to'):
        try:
            qs = qs.filter(created_at__lte=datetime.fromisoformat(request.query_params['date_to']))
        except Exception: pass

    result = []
    for log in qs.order_by('-created_at')[:200]:
        result.append({
            'id': str(log.id), 'action_type': log.action_type,
            'actor': log.actor_username, 'target': log.target_username,
            'task_title': log.task_title, 'classroom_name': log.classroom_name,
            'details': log.details, 'timestamp': log.created_at.isoformat(),
        })
    return Response(result)

# ── ADMIN: Global Announcements ──────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_announcements(request):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
        
    if request.method == 'GET':
        posts = GlobalAnnouncement.objects.all().order_by('-isPinned', '-created_at')
        return Response([{
            'id': str(p.id),
            'title': p.title,
            'message': p.message,
            'targetRole': p.targetRole,
            'isPinned': p.isPinned,
            'createdAt': p.created_at.isoformat()
        } for p in posts])
        
    if request.method == 'POST':
        p = GlobalAnnouncement(
            title=request.data.get('title', 'Announcement'),
            message=request.data.get('message', ''),
            targetRole=request.data.get('targetRole', 'ALL'),
            isPinned=request.data.get('isPinned', False)
        )
        p.save()
        _log('global_broadcast', request.user, details=f'Broadcast: {p.title}')
        return Response({
            'status': 'created',
            'id': str(p.id),
            'title': p.title,
            'isPinned': p.isPinned
        }, status=201)

