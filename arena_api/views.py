# pyre-ignore-all-errors[21]
import random
import string
import os
from datetime import datetime, timedelta, timezone

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from django.contrib.auth.models import User

from .models import (
    CodingTask, CoderProfile, BattleRoom,
    Submission, Classroom, Announcement, Ticket, ActionLog,
    GlobalAnnouncement, UserNotification, FriendRequest,
    Tournament, TournamentQuestion, TournamentMatch, gen_code,
    ReattemptRequest, Exam, ExamSet, ExamViolation, ExamSubmission,
)
from .serializers import (
    CodingTaskSerializer,
    CoderProfileSerializer,
    UserRegistrationSerializer,
)
from rest_framework.exceptions import AuthenticationFailed, NotFound


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
    serializer_class = CodingTaskSerializer
    permission_classes = [IsTeacherOrReadOnly]

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        try:
            obj = queryset.get(**{self.lookup_field: self.kwargs[lookup_url_kwarg]})
        except Exception:
            raise NotFound()
        self.check_object_permissions(self.request, obj)
        return obj

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Check for approved reattempt for the current user
        user_id = str(request.user.id)
        task_id = str(instance.id)

        active_reattempt = ReattemptRequest.objects.filter(
            student_id=user_id,
            task_id=task_id,
            status='approved',
            expires_at__gt=datetime.utcnow()
        ).first()

        data['is_reattempt_approved'] = active_reattempt is not None
        if active_reattempt:
            data['reattempt_expires_at'] = active_reattempt.expires_at.isoformat()

        return Response(data)

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


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_task_complete(request, task_id):
    try:
        task = CodingTask.objects.get(id=task_id)
        if task.content_type == 'Assignment':
            return Response({'error': 'Cannot auto-complete Assignments.'}, status=400)
            
        profile = CoderProfile.objects.get(user_id=str(request.user.id))
        
        # Check if already completed
        existing = [s for s in task.submissions if s.user_id == str(request.user.id) and s.passed]
        if existing:
            return Response({'message': 'Already completed'})
            
        # Create a dummy submission
        sub = Submission(
            user_id=str(request.user.id),
            username=request.user.username,
            code="# Marked as complete automatically\n",
            passed=True,
            score=100.0,
            marks_obtained=task.max_marks,
            status='Submitted',
            review_status='graded'
        )
        task.submissions.append(sub)
        task.save()
        
        # Add XP
        xp_gain = 20 if task.difficulty == 'Easy' else 50 if task.difficulty == 'Medium' else 100
        profile.xp += xp_gain
        profile.recalc_rank()
        profile.save()
        
        return Response({'message': 'Content marked as complete', 'xp_gained': xp_gain})
    except CodingTask.DoesNotExist:
        return Response({'error': 'Task not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)



# â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class UserRegistrationView(generics.CreateAPIView):
    serializer_class   = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def create_teacher(request):
    username = request.data.get('username')
    email = request.data.get('email', '')
    password = request.data.get('password', '').strip()

    if not username:
        return Response({'error': 'Username is required'}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username=username).exists():
        return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)

    if not password:
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
            data['streak'] = getattr(profile, 'streak', 0)
        except CoderProfile.DoesNotExist:
            data['role'] = 'STUDENT'
        return data


class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        refresh = RefreshToken(attrs['refresh'])
        user_id = refresh.payload.get('user_id')
        
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                data['username'] = user.username
                data['user_id'] = str(user.id)
                
                if user.is_superuser:
                    data['role'] = 'ADMIN'
                else:
                    try:
                        profile = CoderProfile.objects.get(user_id=str(user.id))
                        data['role'] = profile.role
                    except CoderProfile.DoesNotExist:
                        data['role'] = 'STUDENT'
            except User.DoesNotExist:
                pass
                
        return data

class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer


# â”€â”€ Profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@api_view(['GET', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def my_profile(request):
    try:
        profile = CoderProfile.objects.get(user_id=str(request.user.id))
    except CoderProfile.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=404)

    if request.method == 'GET':
        data = CoderProfileSerializer(profile).data
        data['username'] = request.user.username
        data['email'] = request.user.email
        data['date_joined'] = request.user.date_joined.isoformat()
        return Response(data)

    # PATCH — update editable profile fields
    email = request.data.get('email')
    if email is not None:
        request.user.email = email.strip()
        request.user.save()

    if 'age' in request.data:
        try:
            profile.age = int(request.data['age'])
        except (ValueError, TypeError):
            pass
    if 'gender' in request.data:
        profile.gender = str(request.data['gender']).strip()
    if 'full_name' in request.data:
        profile.full_name = str(request.data['full_name']).strip()
    if 'reg_no' in request.data:
        profile.reg_no = str(request.data['reg_no']).strip()
    profile.save()

    data = CoderProfileSerializer(profile).data
    data['username'] = request.user.username
    data['email'] = request.user.email
    data['date_joined'] = request.user.date_joined.isoformat()
    return Response(data)


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
        'sequential_labs': getattr(c, 'sequential_labs', False),
        'created_at': c.created_at.isoformat() if c.created_at else None,
        'announcements': [
            {'message': a.message, 'created_at': a.created_at.isoformat(), 'pinned': a.pinned}
            for a in (c.announcements or [])
        ],
    }
    if include_students:
        # Optimization: Safe integer conversion for Django User lookup
        def to_int(v):
            try: return int(v)
            except: return None
            
        uids = [to_int(uid) for uid in (c.student_ids or []) if to_int(uid) is not None]
        student_users = User.objects.filter(id__in=uids).only('id', 'username')
        student_map = {str(u.id): u.username for u in student_users}
        
        d['students'] = [
            {'id': str(uid), 'username': student_map.get(str(uid), 'Unknown User')}
            for uid in (c.student_ids or [])
        ]
    return d


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def classrooms(request):
    """
    GET: Teacher lists their own classrooms with student info (Optimized).
    POST: Teacher creates a new classroom.
    """
    uid = str(request.user.id)
    if request.method == 'GET':
        cs = Classroom.objects.filter(teacher_id=uid)
        
        # Optimization: Pre-fetch student usernames safely
        all_student_ids = set()
        for c in cs:
            all_student_ids.update(c.student_ids or [])
            
        def to_int(v):
            try: return int(v)
            except: return None
            
        uids = [to_int(sid) for sid in all_student_ids if to_int(sid) is not None]
        student_users = User.objects.filter(id__in=uids).only('id', 'username')
        student_map = {str(u.id): u.username for u in student_users}
        
        results = []
        for c in cs:
            data = _classroom_data(c, include_students=False)
            data['students'] = [
                {'id': str(sid), 'username': student_map.get(str(sid), 'Unknown')}
                for sid in (c.student_ids or [])
            ]
            results.append(data)
        return Response(results)

    # POST — create
    name = request.data.get('name', '').strip()
    ctype = request.data.get('type', 'Public')
    if not name:
        return Response({'error': 'name is required'}, status=400)

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    seq = bool(request.data.get('sequential_labs', False))
    c = Classroom(name=name, type=ctype, teacher_id=str(request.user.id), code=code, sequential_labs=seq)
    c.save()
    return Response(_classroom_data(c), status=201)


@api_view(['GET', 'DELETE', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def classroom_detail(request, classroom_id):
    """
    GET    /api/classrooms/<id>/  — get detail (students, announcements, tasks)
    PATCH  /api/classrooms/<id>/  — update name/type/is_locked (teacher only)
    DELETE /api/classrooms/<id>/  — delete classroom (teacher only)
    """
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)

    if request.method == 'GET':
        # include_students=True already parses announcements
        d = _classroom_data(c, include_students=True)
        
        # Fetch associated tasks
        req_user_id = str(request.user.id)
        is_teacher = (str(c.teacher_id) == req_user_id)
        tasks_found = []
        
        # Optimization: Fetch tasks
        all_tasks = CodingTask.objects.filter(id__in=c.task_ids)
        task_map = {str(t.id): t for t in all_tasks}
        
        # Batch fetch reattempt requests for current user
        reattempt_map = {}
        if not is_teacher:
            reattempts = ReattemptRequest.objects.filter(student_id=req_user_id, task_id__in=c.task_ids)
            for r in reattempts:
                tid_str = str(r.task_id)
                if tid_str not in reattempt_map or r.created_at > reattempt_map[tid_str].created_at:
                    reattempt_map[tid_str] = r

        for tid in c.task_ids:
            t = task_map.get(str(tid))
            if not t: continue

            # If teacher, include only ACTIVE submissions in the overview
            # If student, include only their own.
            my_subs = []
            for s in (t.submissions or []):
                matches_user = (str(getattr(s, 'user_id', '')) == req_user_id)
                should_include = (is_teacher and getattr(s, 'is_active', True)) or matches_user
                
                if should_include:
                    sub_data = {
                        'user_id':        str(s.user_id),
                        'username':       getattr(s, 'username', 'Unknown'),
                        'passed':         s.passed,
                        'code':           getattr(s, 'code', ''),
                        'language':       getattr(s, 'language', ''),
                        'score':          s.score,
                        'marks_obtained': s.marks_obtained,
                        'grade':          s.grade,
                        'remarks':        s.remarks,
                        'review_status':  getattr(s, 'review_status', 'graded'),
                        'is_active':      getattr(s, 'is_active', True),
                        'created_at':     s.created_at.isoformat() if getattr(s, 'created_at', None) else None,
                    }
                    if is_teacher or matches_user:
                        sub_data['run_results'] = getattr(s, 'run_results', [])
                    
                    my_subs.append(sub_data)

            # Check reattempt status
            r_req = reattempt_map.get(str(t.id))
            tasks_found.append({
                'id': str(t.id),
                'title': t.title,
                'description': t.description,
                'difficulty': t.difficulty,
                'tech_stack': t.tech_stack,
                'task_type': t.task_type,
                'due_date': t.due_date.isoformat() if t.due_date else None,
                'grading_mode': getattr(t, 'grading_mode', 'Percentage'),
                'grading_type': getattr(t, 'grading_type', 'auto'),
                'max_marks': getattr(t, 'max_marks', 100),
                'pass_criteria': getattr(t, 'pass_criteria', 50),
                'content_type': getattr(t, 'content_type', 'Assignment'),
                'text_content': getattr(t, 'text_content', ''),
                'video_url': getattr(t, 'video_url', ''),
                'submissions': my_subs,
                'reattempt_request': {
                    'status': r_req.status,
                    'expires_at': r_req.expires_at.isoformat() if r_req.expires_at else None
                } if r_req else None
            })

        d['tasks'] = tasks_found
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
        if 'sequential_labs' in request.data:
            c.sequential_labs = bool(request.data['sequential_labs'])
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


@api_view(['DELETE', 'PATCH'])
@permission_classes([IsTeacher])
def delete_announcement(request, classroom_id, ann_index):
    """DELETE/PATCH /api/classrooms/<id>/announcements/<index>/
    DELETE: removes the announcement.
    PATCH:  toggles or sets pinned status (pass {"pinned": true/false}).
    """
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)

    if str(c.teacher_id) != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    idx = int(ann_index)
    if idx < 0 or idx >= len(c.announcements):
        return Response({'error': 'Announcement not found'}, status=404)

    if request.method == 'PATCH':
        pinned = request.data.get('pinned')
        if pinned is None:
            # Toggle
            c.announcements[idx].pinned = not c.announcements[idx].pinned
        else:
            c.announcements[idx].pinned = bool(pinned)
        c.save()
        return Response({'status': 'updated', 'pinned': c.announcements[idx].pinned}, status=200)

    c.announcements.pop(idx)
    c.save()
    return Response({'status': 'deleted'}, status=200)


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
    score      = round(n_passed / total * 100, 1)   # pyre-ignore

    # Apply late submission penalty: -0.5 per day late, floor at 0
    late_days = float(request.data.get('late_days', 0) or 0)
    if late_days > 0:
        penalty = late_days * 0.5
        score   = max(0.0, round(score - penalty, 1))  # pyre-ignore

    # â”€â”€ Grading config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    grading_mode  = getattr(task, 'grading_mode', 'Percentage') or 'Percentage'
    grading_type  = getattr(task, 'grading_type', 'auto') or 'auto'
    max_marks     = float(getattr(task, 'max_marks', 100) or 100)
    is_final      = getattr(task, 'is_final', False)

    if grading_type == 'manual':
        marks_obtained = 0.0
        grade          = ''
        passed         = False
        review_status  = 'pending'
        remarks        = 'Submitted for teacher review. Marks will be assigned by your teacher.'
    else:
        marks_obtained = round(score / 100 * max_marks, 1)  # pyre-ignore
        grade          = task.compute_grade(score) if hasattr(task, 'compute_grade') else ''
        passed         = True if is_final else all_passed
        review_status  = 'graded'
        remarks        = f'Final assessment submitted. Score: {score}%' if is_final else ('All test cases passed.' if all_passed else f'{n_passed}/{total} test cases passed.')

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
        review_status  = review_status,
        is_active      = True,
        status         = 'Submitted',
        run_results    = run_results,
        last_edited_at = now,
        created_at     = now,
    )
    task.submissions.append(new_sub)
    task.save()

    # ── Notify student if manual grading ────────────────────────────────────
    if grading_type == 'manual':
        try:
            UserNotification(
                user_id    = user_id,
                username   = username,
                title      = 'Submission Under Review',
                message    = f'Your submission for "{task.title}" has been received and is being reviewed by your teacher. You will be notified once marks are assigned.',
                notif_type = 'review',
                task_id    = str(task.id),
                task_title = task.title,
            ).save()
        except Exception:
            pass

    # â”€â”€ Award XP to STUDENT profiles only â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    xp_earned = 0
    try:
        prof = CoderProfile.objects.get(user_id=user_id)
        if prof.role == 'STUDENT':
            already_passed = any(
                getattr(s, 'passed', False) and not getattr(s, 'is_active', True)
                for s in task.submissions[:-1]
            )
            if not already_passed and passed:
                xp_earned = int(score)
                prof.xp += xp_earned
                
                # Streak logic
                now_date = datetime.utcnow().date()
                if prof.last_activity_date:
                    last_date = prof.last_activity_date.date()
                    if last_date == now_date - timedelta(days=1):
                        prof.streak += 1
                    elif last_date < now_date - timedelta(days=1):
                        prof.streak = 1
                    # If last_date == now_date, streak stays the same
                else:
                    prof.streak = 1
                
                prof.last_activity_date = datetime.utcnow()
                
                # Update daily activity
                activity = prof.daily_activity or {}
                date_str = now_date.strftime('%Y-%m-%d')
                activity[date_str] = activity.get(date_str, 0) + 1  # pyre-ignore
                prof.daily_activity = activity
                
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

    # ── Gemini AI feedback (only when test cases fail) ─────────────────────────
    ai_feedback = None
    if not all_passed and grading_type == 'auto':
        try:
            gemini_key = os.environ.get('GEMINI_API_KEY', '')
            if gemini_key:
                import urllib.request, json as _json
                tc_summary = '\n'.join(
                    f'TC{j+1}: input={tc.input_data!r}, expected={tc.output_data!r}, '
                    f'got={run_results[j].get("actual_output", "?") if j < len(run_results) else "?"}'
                    f' [{"PASS" if (j < len(run_results) and run_results[j].get("passed")) else "FAIL"}]'
                    for j, tc in enumerate(task.test_cases or [])
                )
                prompt = (
                    f'A student submitted the following {language} code for the problem "{task.title}".\n'
                    f'Problem description: {task.description}\n\n'
                    f'Student\'s code:\n```\n{code[:3000]}\n```\n\n'
                    f'Test case results ({n_passed}/{total} passed):\n{tc_summary}\n\n'
                    f'Give a very short, encouraging hint (2-3 sentences max) pointing out '
                    f'what is wrong and what the student should look into to fix it. '
                    f'Do NOT give away the full solution. Be specific but concise.'
                )
                payload = _json.dumps({
                    'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {'temperature': 0.5, 'maxOutputTokens': 200},
                }).encode()
                gemini_url = (
                    'https://generativelanguage.googleapis.com/v1beta/models/'
                    f'gemini-2.5-flash:generateContent?key={gemini_key}'
                )
                req = urllib.request.Request(
                    gemini_url, data=payload,
                    headers={'Content-Type': 'application/json'}, method='POST'
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    rdata = _json.loads(resp.read())
                ai_feedback = (
                    rdata.get('candidates', [{}])[0]
                    .get('content', {}).get('parts', [{}])[0]
                    .get('text', '').strip()
                ) or None
        except Exception:
            pass  # Gemini feedback is best-effort only

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
        'ai_feedback': ai_feedback,
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


# -- Grade Submission (teacher manually assigns marks) -----------------------

@api_view(['POST'])
@permission_classes([IsTeacher])
def grade_submission(request, task_id):
    """POST /api/tasks/<id>/grade/ — teacher assigns marks for a manual-graded submission."""
    try:
        task = CodingTask.objects.get(id=task_id)
    except Exception:
        return Response({'error': 'Task not found'}, status=404)

    target_user_id = request.data.get('user_id', '')
    try:
        marks_obtained = float(request.data.get('marks_obtained', 0))
    except (ValueError, TypeError):
        return Response({'error': 'Invalid marks value'}, status=400)
    remarks       = str(request.data.get('remarks', '')).strip()
    max_marks     = float(getattr(task, 'max_marks', 100) or 100)
    pass_criteria = float(getattr(task, 'pass_criteria', 50) or 50)

    # Clamp to valid range
    marks_obtained = max(0.0, min(marks_obtained, max_marks))

    updated         = False
    target_username = ''
    for s in (task.submissions or []):
        if s.user_id == target_user_id and getattr(s, 'is_active', True):
            pct              = (marks_obtained / max_marks * 100) if max_marks > 0 else 0
            s.marks_obtained = marks_obtained
            s.score          = round(pct, 1)  # pyre-ignore
            s.grade          = task.compute_grade(pct) if hasattr(task, 'compute_grade') else ''
            s.passed         = marks_obtained >= pass_criteria
            s.remarks        = remarks or f'Marks assigned by teacher: {marks_obtained}/{max_marks}'
            s.review_status  = 'graded'
            s.last_edited_at = datetime.utcnow()
            target_username  = s.username
            updated          = True
            break

    if not updated:
        return Response({'error': 'No active submission found for this student'}, status=404)

    task.save()

    # Notify the student
    try:
        passed_str = 'Passed' if marks_obtained >= pass_criteria else 'Did not pass'
        msg = (
            f'Your teacher graded your submission for "{task.title}". '
            f'You received {marks_obtained}/{max_marks} marks. {passed_str}.'
        )
        if remarks:
            msg += f' Remark: {remarks}'
        UserNotification(
            user_id    = target_user_id,
            username   = target_username,
            title      = 'Marks Assigned',
            message    = msg,
            notif_type = 'graded',
            task_id    = str(task.id),
            task_title = task.title,
        ).save()
    except Exception:
        pass

    return Response({
        'status':          'graded',
        'marks_obtained':  marks_obtained,
        'max_marks':       max_marks,
        'passed':          marks_obtained >= pass_criteria,
    })


# -- User Notifications -------------------------------------------------------

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_notifications(request):
    """GET /api/user-notifications/ — returns this user's notifications (newest first)."""
    user_id = str(request.user.id)
    try:
        notifs = UserNotification.objects.filter(user_id=user_id).order_by('-created_at')[:50]
        return Response([
            {
                'id':         str(n.id),
                'title':      n.title,
                'message':    n.message,
                'notif_type': n.notif_type,
                'is_read':    n.is_read,
                'task_id':    n.task_id,
                'task_title': n.task_title,
                'extra_id':   n.extra_id,
                'extra_name': n.extra_name,
                'created_at': n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifs
        ])
    except Exception:
        return Response([], status=200)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_notification_read(request, notif_id):
    """POST /api/user-notifications/<id>/read/ — mark one notification as read."""
    user_id = str(request.user.id)
    try:
        n = UserNotification.objects.get(id=notif_id, user_id=user_id)
        n.is_read = True
        n.save()
        return Response({'status': 'read'})
    except Exception:
        return Response({'error': 'Not found'}, status=404)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def clear_all_notifications(request):
    """POST /api/user-notifications/clear_all/ — deletes all notifications for this user."""
    user_id = str(request.user.id)
    UserNotification.objects.filter(user_id=user_id).delete()
    return Response({'status': 'cleared'})




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


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def teacher_delete_ticket(request, ticket_id):
    """Allow the teacher who raised a ticket to delete it."""
    try:
        t = Ticket.objects.get(id=ticket_id)
    except Exception:
        return Response({'error': 'Ticket not found'}, status=404)
    if str(t.raised_by_id) != str(request.user.id):
        return Response({'error': 'You can only delete tickets you raised'}, status=403)
    t.delete()
    return Response(status=204)


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




# ── Friends ───────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def friends_list(request):
    """GET /api/friends/ - list current user's confirmed friends."""
    try:
        profile = CoderProfile.objects.get(user_id=str(request.user.id))
    except CoderProfile.DoesNotExist:
        return Response([])
    friend_ids = profile.friends or []
    if not friend_ids:
        return Response([])

    # Batch fetch all usernames in one query
    users = User.objects.filter(id__in=friend_ids).only('id', 'username')
    username_map = {str(u.id): u.username for u in users}

    result = []
    for uid in friend_ids:
        uid_str = str(uid)
        if uid_str in username_map:
            result.append({'id': uid_str, 'username': username_map[uid_str]})
    return Response(result)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def friend_requests_list(request):
    """GET /api/friends/requests/ - list pending incoming friend requests."""
    reqs = FriendRequest.objects.filter(to_user_id=str(request.user.id), status='pending')
    return Response([{
        'id': str(r.id),
        'from_user_id': r.from_user_id,
        'from_username': r.from_username,
        'status': r.status,
        'created_at': r.created_at.isoformat(),
    } for r in reqs])


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def send_friend_request(request):
    """POST /api/friends/request/ - send a friend request by username."""
    target_username = request.data.get('username', '').strip()
    if not target_username:
        return Response({'error': 'username is required'}, status=400)

    try:
        target_user = User.objects.get(username=target_username)
    except User.DoesNotExist:
        return Response({'error': 'User not found.'}, status=404)

    from_id = str(request.user.id)
    to_id = str(target_user.id)

    if from_id == to_id:
        return Response({'error': 'Cannot send a friend request to yourself.'}, status=400)

    try:
        my_prof = CoderProfile.objects.get(user_id=from_id)
        if to_id in (my_prof.friends or []):
            return Response({'error': 'You are already friends with this user.'}, status=400)
    except CoderProfile.DoesNotExist:
        pass

    existing = FriendRequest.objects.filter(from_user_id=from_id, to_user_id=to_id, status='pending').first()
    if existing:
        return Response({'error': 'Friend request already sent.'}, status=400)

    FriendRequest(
        from_user_id=from_id,
        from_username=request.user.username,
        to_user_id=to_id,
    ).save()
    return Response({'message': 'Friend request sent.'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def accept_friend_request(request, req_id):
    """POST /api/friends/requests/<req_id>/accept/"""
    try:
        freq = FriendRequest.objects.get(id=req_id, to_user_id=str(request.user.id), status='pending')
    except FriendRequest.DoesNotExist:
        return Response({'error': 'Friend request not found.'}, status=404)

    freq.status = 'accepted'
    freq.save()

    try:
        UserNotification(
            user_id=freq.from_user_id,
            title="Friend Request Accepted",
            message=f"{request.user.username} accepted your friend request!",
            notif_type="general",
            extra_id=str(request.user.id),
            extra_name=request.user.username
        ).save()
    except Exception as e:
        print("friend accept notification err:", e)

    for uid_a, uid_b in [(freq.to_user_id, freq.from_user_id), (freq.from_user_id, freq.to_user_id)]:
        try:
            p = CoderProfile.objects.get(user_id=uid_a)
            if uid_b not in (p.friends or []):
                p.friends = list(p.friends or []) + [uid_b]
                p.save()
        except CoderProfile.DoesNotExist:
            pass
    return Response({'message': 'Friend request accepted.'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def decline_friend_request(request, req_id):
    """POST /api/friends/requests/<req_id>/decline/"""
    try:
        freq = FriendRequest.objects.get(id=req_id, to_user_id=str(request.user.id), status='pending')
    except FriendRequest.DoesNotExist:
        return Response({'error': 'Friend request not found.'}, status=404)

    freq.status = 'declined'
    freq.save()
    return Response({'message': 'Friend request declined.'})


# ── ADMIN: Classrooms ────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_classrooms(request):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    if request.method == 'POST':
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'error': 'name is required'}, status=400)
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        c = Classroom(name=name, type='Public', teacher_id=str(request.user.id), code=code)
        c.save()
        _log('classroom_created', request.user, classroom=c,
             details=f'Admin created public classroom "{name}".')
        d = _classroom_data(c)
        d['teacher_name'] = request.user.username
        return Response(d, status=201)

    # Optimization: pre-fetch all teacher usernames
    classrooms = list(Classroom.objects.all())
    teacher_ids = {str(c.teacher_id) for c in classrooms}
    teachers = User.objects.filter(id__in=teacher_ids).only('id', 'username')
    teacher_map = {str(u.id): u.username for u in teachers}

    result = []
    for c in classrooms:
        d = _classroom_data(c)
        d['teacher_name'] = teacher_map.get(str(c.teacher_id), '???')
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
        # Auto-delete broadcasts older than 30 days
        cutoff = datetime.now() - timedelta(days=30)
        GlobalAnnouncement.objects.filter(created_at__lt=cutoff).delete()
        
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

@api_view(['PATCH', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def admin_announcement_action(request, aid):
    if not _is_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
        
    try:
        p = GlobalAnnouncement.objects.get(id=aid)
    except Exception:
        return Response({'error': 'Not found'}, status=404)
        
    if request.method == 'PATCH':
        is_pinned = request.data.get('isPinned')
        if is_pinned is not None:
            p.isPinned = is_pinned
            p.save()
            return Response({'status': 'updated'})
        return Response({'error': 'No update data provided'}, status=400)
        
    if request.method == 'DELETE':
        p.delete()
        return Response({'status': 'deleted'})


# ── Reattempt Requests ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def request_reattempt(request):
    """
    POST /api/request-reattempt/
    Body: { "task_id": "..." }
    """
    task_id = request.data.get('task_id')
    if not task_id:
        return Response({'error': 'Task ID required'}, status=400)
        
    try:
        task = CodingTask.objects.get(id=task_id)
    except:
        return Response({'error': 'Task not found'}, status=404)

    uid = str(request.user.id)
    # Check if request already exists
    existing = ReattemptRequest.objects.filter(student_id=uid, task_id=task_id).first()
    if existing:
        if existing.status == 'pending':
            return Response({'error': 'Request already pending'}, status=400)
        if existing.status == 'approved' and existing.expires_at and existing.expires_at > datetime.utcnow():
             return Response({'error': 'Request already approved and active'}, status=400)
        
        # If rejected or expired, re-open
        if existing.status in ['rejected', 'expired', 'approved']:
             existing.status = 'pending'
             existing.created_at = datetime.utcnow()
             existing.save()
             
             try:
                 classroom = Classroom.objects.get(id=task.classroom_id)
                 UserNotification(
                     user_id=classroom.teacher_id,
                     title="Reattempt Request (Re-opened)",
                     message=f"{request.user.username} re-requested a reattempt for '{task.title}'",
                     notif_type="general",
                     task_id=str(task.id),
                     task_title=task.title
                 ).save()
             except Exception as e:
                 print("Notification error:", e)
                 
             return Response({'status': 'Re-opened request'})

    # Get classroom to find teacher
    try:
        classroom = Classroom.objects.get(id=task.classroom_id)
        teacher_id = classroom.teacher_id
    except:
        return Response({'error': 'Classroom not found'}, status=404)
        
    req = ReattemptRequest(
        student_id=uid,
        student_name=request.user.username,
        task_id=task_id,
        task_title=task.title,
        classroom_id=str(classroom.id),
        teacher_id=teacher_id,
        status='pending'
    )
    req.save()
    
    try:
        UserNotification(
            user_id=teacher_id,
            title="Reattempt Request",
            message=f"{request.user.username} requested a reattempt for '{task.title}'",
            notif_type="reattempt_request",
            task_id=str(task.id),
            task_title=task.title,
            extra_id=str(req.id),
            extra_name=request.user.username
        ).save()
    except Exception as e:
        print("Notification error:", e)
        
    return Response({'status': 'Request submitted'})

@api_view(['GET'])
@permission_classes([IsTeacher])
def get_reattempt_requests(request):
    """
    GET /api/reattempt-requests/
    Returns pending reattempt requests for tasks in this teacher's classrooms.
    """
    uid = str(request.user.id)
    reqs = ReattemptRequest.objects.filter(teacher_id=uid, status='pending')
    data = []
    for r in reqs:
        data.append({
            'id': str(r.id),
            'student_id': r.student_id,
            'student_name': r.student_name,
            'task_id': r.task_id,
            'task_title': r.task_title,
            'classroom_id': r.classroom_id,
            'created_at': r.created_at.isoformat(),
        })
    return Response(data)

@api_view(['POST'])
@permission_classes([IsTeacher])
def approve_reattempt(request):
    """
    POST /api/approve-reattempt/
    Body: { "request_id": "...", "action": "approve"|"reject" }
    """
    rid = request.data.get('request_id')
    action = request.data.get('action', 'approve')

    try:
        req = ReattemptRequest.objects.get(id=rid)
    except Exception:
        return Response({'error': 'Request not found'}, status=404)

    if req.teacher_id != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    if action == 'approve':
        req.status = 'approved'
        req.expires_at = datetime.utcnow() + timedelta(days=1)  # 24 hours extension
        notif_title = 'Reattempt Approved'
        notif_msg = (f'Your request to reattempt "{req.task_title}" has been approved! '
                     f'You have 24 hours to reattempt the lab.')
    else:
        req.status = 'rejected'
        req.expires_at = None
        notif_title = 'Reattempt Rejected'
        notif_msg = (f'Your request to reattempt "{req.task_title}" was not approved '
                     f'by your teacher. You may submit another request later.')

    req.save()

    # Notify the student
    try:
        UserNotification(
            user_id    = req.student_id,
            username   = req.student_name,
            title      = notif_title,
            message    = notif_msg,
            notif_type = 'general',
            task_id    = req.task_id,
            task_title = req.task_title,
        ).save()
    except Exception:
        pass

    return Response({'status': f'Request {action}d', 'action': action})


# ── Public Announcements (for students/teachers) ────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def public_announcements(request):
    """GET /api/announcements/ — returns announcements visible to the current user's role."""
    user_role = 'STUDENT'
    try:
        prof = CoderProfile.objects.get(user_id=str(request.user.id))
        user_role = prof.role
    except Exception:
        if request.user.is_superuser:
            user_role = 'ADMIN'

    # Only show announcements from the last 30 days
    cutoff = datetime.now() - timedelta(days=30)
    posts = GlobalAnnouncement.objects.filter(created_at__gte=cutoff).order_by('-isPinned', '-created_at')
    
    result = []
    for p in posts:
        if p.targetRole == 'ALL' or p.targetRole == user_role:
            result.append({
                'id': str(p.id),
                'title': p.title,
                'message': p.message,
                'targetRole': p.targetRole,
                'isPinned': p.isPinned,
                'createdAt': p.created_at.isoformat()
            })
    return Response(result)


# ── Tournaments ────────────────────────────────────────────────────────────────

import uuid


def _tournament_data(t):
    """Serialize a Tournament document to a plain dict."""
    def to_iso(dt_val):
        if not dt_val: return None
        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        return dt_val.isoformat()

    def _match_data(m):
        return {
            'matchId':         m.match_id,
            'roundNum':        m.round_num,
            'player1Id':       m.player1_id,
            'player1Username': m.player1_username,
            'player2Id':       m.player2_id,
            'player2Username': m.player2_username,
            'winnerId':        m.winner_id,
            'winnerUsername':  m.winner_username,
            'status':          m.status,
            'questionIndex':   m.question_index,
        }

    def _question_data(q):
        return {
            'title':       q.title,
            'description': q.description,
            'difficulty':  q.difficulty,
            'testCases': [
                {'input': tc.input_data, 'expected_output': tc.output_data}
                for tc in q.test_cases
            ],
        }

    # Group matches into rounds for the bracket matrix
    rounds_dict = {}
    for m in t.matches:
        rnum = m.round_num
        if rnum not in rounds_dict:
            rounds_dict[rnum] = []
        rounds_dict[rnum].append(_match_data(m))
    
    # Convert to sorted list of round objects
    sorted_rounds = []
    for rnum in sorted(rounds_dict.keys()):
        sorted_rounds.append({
            'roundNumber': rnum,
            'matches': rounds_dict[rnum]
        })

    return {
        'id':                  str(t.id),
        'name':                t.name,
        'code':                t.code,
        'teacherId':           t.teacher_id,
        'teacherUsername':     t.teacher_username,
        'questions':           [_question_data(q) for q in t.questions],
        'participantIds':      list(t.participant_ids),
        'participantUsernames': dict(t.participant_usernames),
        'matches':             [_match_data(m) for m in t.matches],
        'rounds':              sorted_rounds,
        'currentRound':        t.current_round,
        'status':              t.status,
        'winnerId':            t.winner_id,
        'winnerUsername':      t.winner_username,
        'maxPlayers':          t.max_players,
        'description':         t.description or '',
        'startTime':           to_iso(t.start_time),
        'matchDuration':       t.match_duration,
        'xpFirst':             t.xp_first,
        'xpSecond':            t.xp_second,
        'xpThird':             t.xp_third,
        'techStack':           getattr(t, 'tech_stack', 'General'),
        'allowCopyPaste':      getattr(t, 'allow_copy_paste', True),
        'allowTabCompletion':  getattr(t, 'allow_tab_completion', True),
        'isLocked':            t.is_locked,
        'isGlobal':            getattr(t, 'is_global', False),
        'createdAt':           to_iso(t.created_at),
    }


def _generate_round(participant_ids, participant_usernames, round_num, questions, starting_q_index=0):
    """Pair participants randomly; match them to sequential questions."""
    shuffled = list(participant_ids)
    
    # Only shuffle on round 1 to randomize initial seeding
    if round_num == 1:
        random.shuffle(shuffled)
        
    matches = []
    
    # Calculate question assignment
    # Round 1 uses questions[0] ... questions[N/2 - 1]
    # Round 2 uses questions[N/2] ...
    # We need to track which question index we are at.
    # The caller needs to pass the correct starting index for this round?
    # Or we can deduce it if we know the full structure?
    # Simpler: The caller (advance_tournament) usually knows the state.
    # But `t.questions` is a list.
    # Let's assume sequential assignment:
    # Round 1 matches get question 0, 1, 2...
    # But wait, `_generate_round` is called for Round 1.
    # For subsequent rounds, `advance_tournament` calls it.
    
    current_q_idx = starting_q_index

    for i in range(0, len(shuffled), 2):
        p1_id = shuffled[i]
        match_id = f"R{round_num}M{i // 2 + 1}"
        
        # Assign next question if available
        q_idx = 0 
        if current_q_idx < len(questions):
            q_idx = current_q_idx
            current_q_idx += 1
        else:
            # If we run out of unique questions (e.g. fewer questions than matches), fallback to 0 or last
            q_idx = len(questions) - 1 if len(questions) > 0 else 0

        if i + 1 < len(shuffled):
            p2_id = shuffled[i + 1]
            m = TournamentMatch(
                match_id=match_id,
                round_num=round_num,
                player1_id=p1_id,
                player1_username=participant_usernames.get(p1_id, ''),
                player2_id=p2_id,
                player2_username=participant_usernames.get(p2_id, ''),
                status='pending',
                question_index=q_idx,
            )
        else:
            # Bye: player advances automatically
            # Byes don't consume a question usually, as no match happens?
            # Or should we just mark it done?
            m = TournamentMatch(
                match_id=match_id,
                round_num=round_num,
                player1_id=p1_id,
                player1_username=participant_usernames.get(p1_id, ''),
                player2_id='',
                player2_username='',
                winner_id=p1_id,
                winner_username=participant_usernames.get(p1_id, ''),
                status='bye',
                question_index=q_idx, # Assign it but it won't be played
            )
        matches.append(m)
    return matches


@api_view(['POST'])
@permission_classes([IsTeacher])
def create_tournament(request):
    """POST /api/tournaments/ — teacher creates a new tournament."""
    name           = request.data.get('name', '').strip()
    max_players    = int(request.data.get('maxPlayers', 10))
    description    = request.data.get('description', '').strip()
    match_duration = int(request.data.get('matchDuration', 30))
    xp_first       = int(request.data.get('xpFirst', 1000))
    xp_second      = int(request.data.get('xpSecond', 600))
    xp_third       = int(request.data.get('xpThird', 300))
    
    tech_stack           = request.data.get('techStack', 'General')
    allow_copy_paste     = request.data.get('allowCopyPaste', True)
    allow_tab_completion = request.data.get('allowTabCompletion', True)

    provided_questions = request.data.get('questions', [])

    # Optional ISO start_time
    start_time_str = request.data.get('startTime', None)
    is_global      = request.data.get('isGlobal', False)
    
    # Permission check for global
    profile = CoderProfile.objects.filter(user_id=str(request.user.id)).first()
    is_admin = request.user.is_superuser or (profile and profile.role == 'ADMIN')
    
    if is_global and not is_admin:
        return Response({'error': 'Only admins can create global tournaments'}, status=403)

    start_time = None
    if start_time_str:
        try:
            from datetime import datetime as dt
            start_time = dt.fromisoformat(start_time_str.replace('Z', '+00:00'))
        except ValueError:
            return Response({'error': 'Invalid startTime format; use ISO 8601'}, status=400)

    if not name:
        return Response({'error': 'name required'}, status=400)

    questions = []
    
    if provided_questions and isinstance(provided_questions, list):
        # Use provided questions
        from .models import TestCase as TC
        for pq in provided_questions:
            tcs = []
            for tc in pq.get('testCases', []):
                tcs.append(TC(
                    input_data=tc.get('input', ''),
                    output_data=tc.get('expected_output', '')
                ))
            
            questions.append(TournamentQuestion(
                title=pq.get('title', 'Untitled Question'),
                description=pq.get('description', ''),
                difficulty=pq.get('difficulty', 'Easy'),
                test_cases=tcs
            ))
    else:
        # Generate placeholders if no questions provided
        # Calculate required questions based on max players (Binary Tree: N-1 matches = N-1 questions)
        num_questions_needed = max_players - 1
        current_round_matches = max_players // 2
        round_num = 1
        
        while current_round_matches >= 1:
            for m in range(current_round_matches):
                q_title = f"Round {round_num} - Match {m+1}" if current_round_matches > 1 else "Final Round"
                questions.append(TournamentQuestion(
                    title=q_title,
                    description="Teacher needs to add description here.",
                    difficulty="Easy",
                    test_cases=[]
                ))
            current_round_matches //= 2
            round_num += 1

    code = gen_code(6)
    t = Tournament(
        name=name,
        code=code,
        teacher_id=str(request.user.id),
        teacher_username=request.user.username,
        max_players=max(2, min(max_players, 32)),
        description=description,
        questions=questions,
        start_time=start_time,
        match_duration=max(5, min(match_duration, 180)),
        xp_first=max(0, xp_first),
        xp_second=max(0, xp_second),
        xp_third=max(0, xp_third),
        tech_stack=tech_stack,
        allow_copy_paste=allow_copy_paste,
        allow_tab_completion=allow_tab_completion,
        is_global=is_global,
    )
    t.save()
    return Response(_tournament_data(t), status=201)


@api_view(['GET'])
@permission_classes([IsTeacher])
def my_tournaments(request):
    """GET /api/tournaments/my/ — list teacher's tournaments."""
    ts = Tournament.objects.filter(teacher_id=str(request.user.id))
    return Response([_tournament_data(t) for t in ts])


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def joined_tournaments(request):
    """GET /api/tournaments/joined/ — student's joined tournaments."""
    uid = str(request.user.id)
    ts = Tournament.objects.filter(participant_ids=uid)
    return Response([_tournament_data(t) for t in ts])


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def public_tournaments(request):
    """GET /api/tournaments/public/ — list active global tournaments for discovery."""
    ts = Tournament.objects.filter(is_global=True, status='waiting')
    return Response([_tournament_data(t) for t in ts])

def _try_auto_start_tournament(t):
    """Helper: Transitions tournament from waiting -> active if conditions met."""
    if t.status != 'waiting':
        return False
    
    # Must have questions (placeholder check)
    req_q_count = len(t.participant_ids) - 1
    if len(t.questions) < req_q_count:
        return False
        
    for i in range(req_q_count):
        if not t.questions[i].test_cases:
            return False # Wait until filled

    # Must have at least 2 participants
    if len(t.participant_ids) < 2:
        return False
    
    # Start it
    t.current_round = 1
    t.status = 'active'
    if not t.start_time:
         t.start_time = datetime.now(timezone.utc)
    
    t.matches = _generate_round(
        t.participant_ids,
        dict(t.participant_usernames),
        1,
        t.questions,
        starting_q_index=0
    )
    t.save()
    return True

@api_view(['GET', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def tournament_detail(request, tournament_id):
    """GET/DELETE /api/tournaments/<id>/"""
    try:
        t = Tournament.objects.get(id=tournament_id)
    except Exception:
        return Response({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        # Auto-start check (time-based)
        if t.status == 'waiting' and t.start_time:
             now = datetime.now(timezone.utc)
             if t.start_time.tzinfo is None:
                 # Assume UTC if naive, to be safe
                 t.start_time = t.start_time.replace(tzinfo=timezone.utc)
             if t.start_time <= now:
                 _try_auto_start_tournament(t)

        return Response(_tournament_data(t))

    if request.method == 'DELETE':
        if t.teacher_id != str(request.user.id) and not request.user.is_superuser:
            return Response({'error': 'Forbidden'}, status=403)
        t.delete()
        return Response({'status': 'deleted'})


@api_view(['POST'])
@permission_classes([IsTeacher])
def add_tournament_question(request, tournament_id):
    """POST /api/tournaments/<id>/questions/ — update an existing placeholder question or add new."""
    try:
        t = Tournament.objects.get(id=tournament_id)
    except Exception:
        return Response({'error': 'Not found'}, status=404)
    if t.teacher_id != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    title       = request.data.get('title', '').strip()
    description = request.data.get('description', '').strip()
    difficulty  = request.data.get('difficulty', 'Easy')
    raw_tc      = request.data.get('testCases', [])
    q_index     = request.data.get('questionIndex', -1) # Optional index to update

    if not title or not description:
        return Response({'error': 'title and description required'}, status=400)

    from .models import TestCase as TC
    test_cases = [
        TC(input_data=tc.get('input', ''), output_data=tc.get('expected_output', ''))
        for tc in raw_tc
    ]
    
    q_data = TournamentQuestion(
        title=title,
        description=description,
        difficulty=difficulty,
        test_cases=test_cases,
    )
    
    # If valid index provided, update that question
    if 0 <= q_index < len(t.questions):
        t.questions[q_index] = q_data
    else:
        # Otherwise append new (fallback)
        t.questions.append(q_data)

    t.save()
    return Response(_tournament_data(t))


@api_view(['DELETE'])
@permission_classes([IsTeacher])
def remove_tournament_question(request, tournament_id, q_idx):
    """DELETE /api/tournaments/<id>/questions/<idx>/"""
    try:
        t = Tournament.objects.get(id=tournament_id)
    except Exception:
        return Response({'error': 'Not found'}, status=404)
    if t.teacher_id != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        q_idx = int(q_idx)
        t.questions.pop(q_idx)
    except (IndexError, ValueError):
        return Response({'error': 'Invalid index'}, status=400)

    t.save()
    return Response(_tournament_data(t))


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def join_tournament(request):
    """POST /api/tournaments/join/ — student joins with {code}."""
    code = request.data.get('code', '').strip().upper()
    tournament_id = request.data.get('tournament_id')
    
    t = None
    if tournament_id:
        try:
            t = Tournament.objects.get(id=tournament_id)
        except:
            return Response({'error': 'Tournament not found'}, status=404)
    elif code:
        try:
            t = Tournament.objects.get(code=code)
        except Exception:
            return Response({'error': 'Tournament not found'}, status=404)
    else:
        return Response({'error': 'Tournament ID or code required'}, status=400)

    if t.status != 'waiting':
        return Response({'error': 'Tournament has already started'}, status=400)

    if t.is_locked:
        return Response({'error': 'Participant list is locked'}, status=400)

    uid = str(request.user.id)
    if uid in t.participant_ids:
        return Response(_tournament_data(t))  # already joined

    if len(t.participant_ids) >= t.max_players:
        return Response({'error': 'Tournament is full'}, status=400)

    t.participant_ids.append(uid)
    usernames = dict(t.participant_usernames)
    usernames[uid] = request.user.username
    t.participant_usernames = usernames
    
    # Auto-start check (capacity)
    if len(t.participant_ids) >= t.max_players:
        # Try starting if full
        did_start = _try_auto_start_tournament(t)
        if not did_start:
             t.save() # Just save the new participant if failed to start (e.g. no questions)
    else:
        t.save()

    return Response(_tournament_data(t))


@api_view(['POST'])
@permission_classes([IsTeacher])
def start_tournament(request, tournament_id):
    """POST /api/tournaments/<id>/start/ — generate round 1 bracket."""
    try:
        t = Tournament.objects.get(id=tournament_id)
    except Exception:
        return Response({'error': 'Not found'}, status=404)
    if t.teacher_id != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)
    if t.status != 'waiting':
        return Response({'error': 'Tournament already started'}, status=400)
    if len(t.participant_ids) < 2:
        return Response({'error': 'Need at least 2 participants'}, status=400)

    # Determine required number of active questions (N-1 for single elimination)
    req_q_count = len(t.participant_ids) - 1
    
    if len(t.questions) < req_q_count:
        return Response({'error': f'Not enough question slots. Need {req_q_count}.'}, status=400)

    # Verify that the required questions have test cases (are not empty placeholders)
    for i in range(req_q_count):
        if not t.questions[i].test_cases:
            return Response({
                'error': f'Question {i+1} ("{t.questions[i].title}") is empty. Please add test cases before starting.'
            }, status=400)

    t.current_round = 1
    t.status = 'active'
    t.matches = _generate_round(
        t.participant_ids,
        dict(t.participant_usernames),
        1,
        t.questions,
        starting_q_index=0
    )
    t.save()
    return Response(_tournament_data(t))


@api_view(['POST'])
@permission_classes([IsTeacher])
def advance_tournament(request, tournament_id):
    """POST /api/tournaments/<id>/advance/ — collect winners of current round and start next."""
    try:
        t = Tournament.objects.get(id=tournament_id)
    except Exception:
        return Response({'error': 'Not found'}, status=404)
    if t.teacher_id != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)
    if t.status != 'active':
        return Response({'error': 'Tournament not active'}, status=400)

    current_matches = [m for m in t.matches if m.round_num == t.current_round]
    # All current-round matches must be resolved (done or bye)
    unresolved = [m for m in current_matches if m.status not in ('done', 'bye')]
    if unresolved:
        return Response({
            'error': 'Not all matches are finished yet',
            'pending': [m.match_id for m in unresolved],
        }, status=400)

    winners = [m.winner_id for m in current_matches if m.winner_id]

    if len(winners) == 1:
        # Tournament over — we have a champion
        t.status = 'done'
        t.winner_id = winners[0]
        t.winner_username = dict(t.participant_usernames).get(winners[0], '')
        t.save()

        # Award XP to top 3 finishers
        try:
            # 1st: champion
            first_id = winners[0]

            # 2nd: whoever lost the final match (same round, the other player)
            final_match = next(
                (m for m in current_matches if m.winner_id == first_id and m.status == 'done'),
                None
            )
            second_id = None
            if final_match:
                second_id = final_match.player2_id if final_match.player1_id == first_id else final_match.player1_id

            # 3rd: losers from the semi-final round (round before current)
            third_ids = []
            if t.current_round > 1:
                semi_matches = [m for m in t.matches if m.round_num == t.current_round - 1]
                third_ids = [
                    (m.player2_id if m.winner_id == m.player1_id else m.player1_id)
                    for m in semi_matches
                    if m.status == 'done' and m.winner_id
                ]

            def _award_xp(uid, amount):
                if not uid or not amount:
                    return
                try:
                    profile = CoderProfile.objects.get(user_id=uid)
                    profile.xp = (profile.xp or 0) + amount
                    profile.recalc_rank()
                    profile.save()
                except Exception:
                    pass

            _award_xp(first_id, t.xp_first)
            _award_xp(second_id, t.xp_second)
            for tid in third_ids:
                _award_xp(tid, t.xp_third)
        except Exception:
            pass  # XP errors must never block the tournament result

        return Response(_tournament_data(t))

    # Calculate next question index
    last_idx = -1
    for m in t.matches:
        if m.question_index > last_idx:
            last_idx = m.question_index
            
    next_start_idx = last_idx + 1
    
    # Check if we have enough questions (next round needs len(winners)//2 questions)
    needed = len(winners) // 2
    if next_start_idx + needed > len(t.questions):
        # We might have fewer questions generated than needed if max_players was small initially?
        # But create_tournament generates for max_players.
        pass

    next_round = t.current_round + 1
    new_matches = _generate_round(
        winners,
        dict(t.participant_usernames),
        next_round,
        t.questions,
        starting_q_index=next_start_idx
    )
    t.matches = list(t.matches) + new_matches
    t.current_round = next_round
    t.save()
    return Response(_tournament_data(t))


@api_view(['POST'])
@permission_classes([IsTeacher])
def decide_match_winner(request, tournament_id, match_id):
    """POST /api/tournaments/<id>/matches/<match_id>/decide/ — teacher resolves a tie."""
    try:
        t = Tournament.objects.get(id=tournament_id)
    except Exception:
        return Response({'error': 'Not found'}, status=404)
    if t.teacher_id != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    winner_id = request.data.get('winnerId', '').strip()
    if not winner_id:
        return Response({'error': 'winnerId required'}, status=400)

    updated = False
    for m in t.matches:
        if m.match_id == match_id:
            if winner_id not in (m.player1_id, m.player2_id):
                return Response({'error': 'winnerId is not a participant in this match'}, status=400)
            m.winner_id = winner_id
            m.winner_username = dict(t.participant_usernames).get(winner_id, '')
            m.status = 'done'
            updated = True
            break

    if not updated:
        return Response({'error': 'Match not found'}, status=404)

    t.save()
    return Response(_tournament_data(t))


@api_view(['POST'])
@permission_classes([IsTeacher])
def lock_tournament(request, tournament_id):
    """POST /api/tournaments/<id>/lock/ — toggle participant lock."""
    try:
        t = Tournament.objects.get(id=tournament_id)
    except Exception:
        return Response({'error': 'Not found'}, status=404)
    if t.teacher_id != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)
    if t.status != 'waiting':
        return Response({'error': 'Can only lock a waiting tournament'}, status=400)

    t.is_locked = not t.is_locked
    t.save()
    return Response(_tournament_data(t))


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_leaderboard(request):
    """GET /api/leaderboard/ — top students by XP."""
    limit = int(request.query_params.get('limit', 100))
    profiles = list(CoderProfile.objects.filter(role='STUDENT').order_by('-xp')[:limit])
    
    # Batch fetch all usernames in one query
    user_ids = [str(p.user_id) for p in profiles]
    users = User.objects.filter(id__in=user_ids).only('id', 'username')
    username_map = {str(u.id): u.username for u in users}

    leaderboard = []
    for i, p in enumerate(profiles):
        uid_str = str(p.user_id)
        leaderboard.append({
            'rank': i + 1,
            'user_id': uid_str,
            'username': username_map.get(uid_str, "???"),
            'xp': p.xp,
            'level': p.level,
            'rank_name': p.rank
        })
        
    return Response(leaderboard)

# ── Exams ──────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsTeacher])
def create_exam(request):
    data = request.data
    classroom_id = data.get('classroom_id')
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)
        
    if str(c.teacher_id) != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)

    # Safe date parsing
    def parse_dt(val):
        if not val: return None
        try:
            return datetime.fromisoformat(val.replace('Z', '+00:00'))
        except Exception:
            return None

    exam = Exam(
        title=data.get('title'),
        description=data.get('description', ''),
        classroom_id=classroom_id,
        teacher_id=str(request.user.id),
        duration_minutes=int(data.get('duration_minutes', 60)),
        start_time=parse_dt(data.get('start_time')),
        end_time=parse_dt(data.get('end_time')),
        random_assignment=bool(data.get('randomize_sets', data.get('random_assignment', True))), # Map randomize_sets
        allow_copy_paste=bool(data.get('allow_copy_paste', False)),
        allow_tab_completion=bool(data.get('allow_tab_completion', False)),
        fullscreen_required=bool(data.get('require_fullscreen', data.get('fullscreen_required', True))), # Map require_fullscreen
        primary_language=data.get('primary_language', 'Python'),
        pass_threshold_test_cases=int(data.get('pass_threshold_test_cases', 2))
    )

    if not exam.start_time or not exam.end_time:
        return Response({'error': 'Start time and End time are required and must be valid dates.'}, status=400)
    
    sets_data = data.get('sets', [])
    for sd in sets_data:
        es = ExamSet(name=sd.get('name', 'A'), question_ids=sd.get('question_ids', []))
        exam.sets.append(es)

    exam.save()
    return Response({'message': 'Exam created successfully', 'id': str(exam.id)}, status=201)

def _exam_data(e, include_sets=False, user_role='STUDENT', user_id=None):
    data = {
        'id': str(e.id),
        'title': e.title,
        'description': e.description,
        'classroom_id': e.classroom_id,
        'teacher_id': e.teacher_id,
        'duration_minutes': e.duration_minutes,
        'start_time': e.start_time.isoformat() if e.start_time else None,
        'end_time': e.end_time.isoformat() if e.end_time else None,
        'allow_copy_paste': e.allow_copy_paste,
        'allow_tab_completion': e.allow_tab_completion,
        'fullscreen_required': e.fullscreen_required,
        'pass_threshold_test_cases': e.pass_threshold_test_cases,
        'primary_language': getattr(e, 'primary_language', 'Python'),
    }
    
    if include_sets or user_role in ['TEACHER', 'ADMIN']:
        data['sets'] = [{'name': s.name, 'question_ids': s.question_ids} for s in e.sets]
        
    # include submission status if requested for student
    if user_role == 'STUDENT' and user_id:
        sub = ExamSubmission.objects.filter(exam_id=str(e.id), student_id=str(user_id)).order_by('-started_at').first()
        if sub:
            data['submission_status'] = sub.status
            data['warnings_left'] = sub.warnings_left
            if sub.status == 'in_progress':
                # Check if time is up
                elapsed = (datetime.utcnow() - sub.started_at).total_seconds() / 60
                if elapsed > getattr(e, 'duration_minutes', 60) or datetime.utcnow() > e.end_time:
                    data['submission_status'] = 'expired'
            
    return data

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_exams(request, classroom_id):
    try:
        c = Classroom.objects.get(id=classroom_id)
    except Exception:
        return Response({'error': 'Classroom not found'}, status=404)
    
    exams = Exam.objects.filter(classroom_id=classroom_id, is_active=True)
    
    profile = CoderProfile.objects.filter(user_id=str(request.user.id)).first()
    role = profile.role if profile else 'STUDENT'
    
    res = []
    for e in exams:
        res.append(_exam_data(e, user_role=role, user_id=str(request.user.id)))
        
    return Response(res)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def start_exam_session(request, exam_id):
    try:
        # Get the exam; ignore is_active if it's missing or set to True by default
        exam = Exam.objects.get(id=exam_id)
        if hasattr(exam, 'is_active') and not exam.is_active:
             return Response({'error': 'Exam is currently disabled by teacher'}, status=403)
    except Exception:
        return Response({'error': 'Exam not found'}, status=404)
        
    now = datetime.utcnow()
    # 2 minute grace period for start time to account for clock drift
    start_time_grace = (exam.start_time - timedelta(minutes=2)).replace(tzinfo=None) if exam.start_time else None
    end_time_naive = exam.end_time.replace(tzinfo=None) if exam.end_time else None
    
    if start_time_grace and now < start_time_grace:
        return Response({'error': f'Exam has not started yet. It starts at {exam.start_time.isoformat()}'}, status=400)
    if end_time_naive and now > end_time_naive:
        return Response({'error': 'Exam has ended'}, status=400)
        
    uid = str(request.user.id)
    # Check existing
    sub = ExamSubmission.objects.filter(exam_id=exam_id, student_id=uid).order_by('-started_at').first()
    if sub:
        if sub.status == 'in_progress':
            # return existing session info
            elapsed = (now - sub.started_at).total_seconds() / 60
            if elapsed > getattr(exam, 'duration_minutes', 60):
                sub.status = 'forced_submitted'
                sub.submitted_at = now
                sub.save()
                return Response({'error': 'Exam time expired'}, status=400)
                
            # fetch questions for the assigned set
            questions = []
            assigned_set = next((s for s in exam.sets if s.name == sub.set_id), None)
            if assigned_set:
                for qid in assigned_set.question_ids:
                    try:
                        q = CodingTask.objects.get(id=qid)
                        questions.append({
                            'id': str(q.id),
                            'title': q.title,
                            'description': q.description,
                            'test_cases': [{'input_data': tc.input_data, 'output_data': tc.output_data, 'is_hidden': tc.is_hidden} for tc in q.test_cases]
                        })
                    except Exception:
                        pass
                        
            return Response({
                'message': 'Resumed existing session',
                'submission_id': str(sub.id),
                'set_id': sub.set_id,
                'warnings_left': sub.warnings_left,
                'answers': sub.answers,
                'start_time': sub.started_at.isoformat(),
                'questions': questions,
                'exam': _exam_data(exam)
            })
        elif sub.status == 'archived':
            # A teacher has granted a re-attempt. Allow creating a fresh session.
            sub = None
        else:
            return Response({'error': 'Exam already submitted'}, status=400)
            
    # Start new session if no active session exists (or re-attempt granted)
    assigned_set = None
    if exam.random_assignment and len(exam.sets) > 0:
        assigned_set = random.choice(exam.sets)
    elif len(exam.sets) > 0:
        assigned_set = exam.sets[0]
        
    if not assigned_set:
         return Response({'error': 'Exam has no question sets'}, status=400)
         
    sub = ExamSubmission(
        exam_id=str(exam.id),
        student_id=uid,
        student_username=request.user.username,
        set_id=assigned_set.name,
        answers={},
        warnings_left=3,
        status='in_progress',
        started_at=now
    )
    sub.save()
    
    questions = []
    for qid in assigned_set.question_ids:
        try:
            q = CodingTask.objects.get(id=qid)
            questions.append({
                'id': str(q.id),
                'title': q.title,
                'description': q.description,
                'test_cases': [{'input_data': tc.input_data, 'output_data': tc.output_data, 'is_hidden': tc.is_hidden} for tc in q.test_cases]
            })
        except Exception:
            pass
            
            
    return Response({
        'message': 'Session started',
        'submission_id': str(sub.id),
        'set_id': sub.set_id,
        'warnings_left': sub.warnings_left,
        'answers': {},
        'start_time': sub.started_at.isoformat(),
        'questions': questions,
        'exam': _exam_data(exam)
    })

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def submit_exam_question(request, exam_id):
    """Saves code for a single question."""
    uid = str(request.user.id)
    try:
        sub = ExamSubmission.objects.filter(exam_id=exam_id, student_id=uid, status='in_progress').order_by('-started_at').first()
        if not sub:
            return Response({
                'error': 'Active session not found',
                'debug': f'Exam: {exam_id}, Student: {uid}'
            }, status=404)
    except Exception as e:
        return Response({'error': f'Database error: {str(e)}'}, status=500)
        
    exam = Exam.objects.get(id=exam_id)
    now = datetime.utcnow()
    elapsed = (now - sub.started_at).total_seconds() / 60
    end_time_naive = exam.end_time.replace(tzinfo=None) if exam.end_time else None

    if elapsed > getattr(exam, 'duration_minutes', 60) or (end_time_naive and now > end_time_naive):
         sub.status = 'forced_submitted'
         sub.submitted_at = now
         sub.save()
         return Response({'error': 'Exam time expired'}, status=400)

    data = request.data
    q_id = data.get('question_id')
    code = data.get('code')
    language = data.get('language')
    passed_count = data.get('passed_count', 0)
    total_cases = data.get('total_test_cases', 0)
    
    if not q_id:
        return Response({'error': 'question_id is required'}, status=400)
        
    sub.answers[str(q_id)] = {
        'code': code,
        'language': language,
        'passed_count': passed_count,
        'total_test_cases': total_cases,
        'status': 'saved'
    }
    sub.save()
    return Response({'message': 'Progress saved'})

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def log_exam_violation(request, exam_id):
    uid = str(request.user.id)
    try:
        sub = ExamSubmission.objects.filter(exam_id=exam_id, student_id=uid, status='in_progress').order_by('-started_at').first()
        if not sub:
            return Response({
                'error': 'Active session not found',
                'debug': f'Exam: {exam_id}, Student: {uid}'
            }, status=404)
    except Exception as e:
        return Response({'error': f'Database error: {str(e)}'}, status=500)
    
    # Already forced - don't allow further violations
    if sub.status != 'in_progress':
        return Response({'forced': True, 'malpractice': True}, status=403)
        
    vtype = request.data.get('type')
    VALID_TYPES = ['tab_switch', 'fullscreen_exit', 'screenshot_attempt', 'copy_paste']
    if vtype not in VALID_TYPES:
        return Response({'error': 'Invalid violation type'}, status=400)

    VIOLATION_LABELS = {
        'tab_switch': 'Tab Switch',
        'fullscreen_exit': 'Fullscreen Exit',
        'screenshot_attempt': 'Screenshot Attempt',
        'copy_paste': 'Copy/Paste Attempt',
    }
    label = VIOLATION_LABELS.get(vtype, vtype)

    sub.violations.append(ExamViolation(type=vtype, timestamp=datetime.utcnow()))
    sub.warnings_left = max(0, sub.warnings_left - 1)

    is_forced = sub.warnings_left <= 0

    if is_forced:
        sub.status = 'malpractice'
        sub.submitted_at = datetime.utcnow()
        sub.manual_evaluation_needed = True
        sub.save()

        # Notify teacher of forced expulsion
        try:
            exam = Exam.objects.get(id=exam_id)
            
            # Tally all violations for the teacher report
            from collections import Counter
            tally = Counter([v.type for v in sub.violations])
            tally_str = ", ".join([f"{count}x {VIOLATION_LABELS.get(k, k)}" for k, count in tally.items()])
            
            UserNotification(
                user_id=exam.teacher_id,
                title='🚨 MALPRACTICE ALERT — Student Expelled',
                message=(
                    f'{sub.student_username} was automatically expelled from "{exam.title}" '
                    f'after exceeding the maximum violation limit.\n'
                    f'Violation History: {tally_str}.\n'
                    f'Final trigger: {label}. Exam submission has been locked.'
                ),
                notif_type='general',
                extra_id=str(sub.id),
                extra_name=sub.student_username,
            ).save()
        except Exception:
            pass

        return Response({
            'forced': True,
            'malpractice': True,
            'message': 'You have been removed from the exam for repeated violations.'
        }, status=403)

    sub.save()

    # Notify teacher of each individual violation
    try:
        exam = Exam.objects.get(id=exam_id)
        violations_count = 3 - sub.warnings_left
        UserNotification(
            user_id=exam.teacher_id,
            title=f'⚠️ Exam Violation — {sub.student_username}',
            message=(
                f'{sub.student_username} triggered a "{label}" violation during '
                f'"{exam.title}". Warnings remaining: {sub.warnings_left}/3 '
                f'(violation {violations_count}/3).'
            ),
            notif_type='general',
            extra_id=str(sub.id),
            extra_name=sub.student_username,
        ).save()
    except Exception:
        pass

    return Response({'warnings_left': sub.warnings_left, 'forced': False, 'malpractice': False})

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def finalize_exam(request, exam_id):
    uid = str(request.user.id)
    try:
        # First, find any attempt for this student
        sub = ExamSubmission.objects.filter(exam_id=exam_id, student_id=uid).order_by('-started_at').first()
        
        if not sub:
            return Response({
                'error': 'Active session not found',
                'debug': f'No submission record found for Exam:{exam_id} Student:{uid}'
            }, status=404)
            
        if sub.status in ['submitted', 'forced_submitted', 'malpractice']:
            return Response({'message': 'Exam already submitted', 'already_done': True})
            
        if sub.status != 'in_progress':
             return Response({'error': f'Invalid session status: {sub.status}'}, status=400)
    except Exception as e:
        return Response({'error': f'Database error: {str(e)}'}, status=500)
         
    data = request.data
    # Optional update of last question answers
    q_id = data.get('question_id')
    if q_id:
        sub.answers[str(q_id)] = {
            'code': data.get('code'),
            'language': data.get('language'),
            'passed_count': data.get('passed_count', 0),
            'total_test_cases': data.get('total_test_cases', 0),
            'status': 'submitted'
        }
        
    sub.status = 'submitted'
    sub.submitted_at = datetime.utcnow()
    sub.manual_evaluation_needed = True # flag for teacher
    
    # Calculate simple total marks (percentage of tests passed out of total)
    total_tests = 0
    passed = 0
    for qid, ans in sub.answers.items():
        total_tests += ans.get('total_test_cases', 0)
        passed += ans.get('passed_count', 0)
        
    if total_tests > 0:
        sub.total_marks = round((passed / total_tests) * 100, 2)
        
    sub.save()
    return Response({'message': 'Exam submitted successfully'})

@api_view(['GET', 'PATCH'])
@permission_classes([IsTeacher])
def exam_submissions(request, exam_id):
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exception:
        return Response({'error': 'Exam not found'}, status=404)
        
    if str(exam.teacher_id) != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)
        
    if request.method == 'GET':
        # Default to latest attempts first, excluding archived ones to avoid confusion during re-attempts
        subs = ExamSubmission.objects.filter(exam_id=exam_id, status__ne='archived').order_by('-started_at')
        res = []
        for s in subs:
            res.append({
                'id': str(s.id),
                'student_id': s.student_id,
                'student_username': s.student_username,
                'set_id': s.set_id,
                'answers': s.answers,
                'violations': [{'type': v.type, 'timestamp': v.timestamp.isoformat()} for v in s.violations],
                'warnings_left': s.warnings_left,
                'status': s.status,
                'total_marks': s.total_marks,
                'manual_evaluation_needed': s.manual_evaluation_needed,
                'started_at': s.started_at.isoformat() if s.started_at else None,
                'submitted_at': s.submitted_at.isoformat() if s.submitted_at else None,
            })
        return Response(res)
        
    elif request.method == 'PATCH':
        sub_id = request.data.get('submission_id')
        try:
             sub = ExamSubmission.objects.get(id=sub_id, exam_id=exam_id)
        except Exception:
             return Response({'error': 'Submission not found'}, status=404)
             
        if 'total_marks' in request.data:
             sub.total_marks = float(request.data['total_marks'])
             sub.manual_evaluation_needed = False
             
        sub.save()
        return Response({'message': 'Grade updated'})

@api_view(['POST'])
@permission_classes([IsTeacher])
def grant_exam_reattempt(request, exam_id):
    """Archives a submission so the student can start a new session."""
    sub_id = request.data.get('submission_id')
    try:
        sub = ExamSubmission.objects.get(id=sub_id, exam_id=exam_id)
        sub.status = 'archived'
        sub.save()
        return Response({'message': 'Re-attempt granted. User can now start a new session.'})
    except Exception as e:
        return Response({'error': str(e)}, status=404)

@api_view(['GET', 'PUT', 'DELETE', 'PATCH'])
@permission_classes([IsTeacher])
def exam_detail(request, exam_id):
    """GET, PUT, PATCH, DELETE /api/exams/<id>/ — Teacher action on exam."""
    try:
        e = Exam.objects.get(id=exam_id)
    except Exception:
        return Response({'error': 'Exam not found'}, status=404)
        
    if str(e.teacher_id) != str(request.user.id):
        return Response({'error': 'Forbidden'}, status=403)
        
    if request.method == 'GET':
        return Response(_exam_data(e, include_sets=True, user_role='TEACHER'))
        
    elif request.method in ['PUT', 'PATCH']:
        data = request.data
        e.title = data.get('title', e.title)
        e.description = data.get('description', e.description)
        e.duration_minutes = int(data.get('duration_minutes', e.duration_minutes))
        
        # Safe date parsing
        def parse_dt(val):
            if not val: return None
            try:
                return datetime.fromisoformat(val.replace('Z', '+00:00'))
            except Exception:
                return None

        if data.get('start_time'):
            e.start_time = parse_dt(data['start_time'])
        if data.get('end_time'):
            e.end_time = parse_dt(data['end_time'])
            
        e.random_assignment = data.get('randomize_sets', e.random_assignment) # Field name match
        e.allow_copy_paste = data.get('allow_copy_paste', e.allow_copy_paste)
        e.allow_tab_completion = data.get('allow_tab_completion', e.allow_tab_completion)
        e.fullscreen_required = data.get('require_fullscreen', e.fullscreen_required) # Field name match
        e.primary_language = data.get('primary_language', e.primary_language) 
        
        if 'sets' in data:
            e.sets = []
            for sd in data.get('sets', []):
                es = ExamSet(name=sd.get('name', 'A'), question_ids=sd.get('question_ids', []))
                e.sets.append(es)
                
        e.save()
        return Response({'message': 'Exam updated successfully'})
        
    elif request.method == 'DELETE':
        e.is_active = False # Soft delete
        e.save()
        return Response({'message': 'Exam deleted successfully'})
