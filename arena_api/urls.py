from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .health import health_check

router = DefaultRouter()
router.register(r'tasks', views.CodingTaskViewSet, basename='codingtask')

urlpatterns = [
    path('', include(router.urls)),

    # Health Check
    path('health/',                health_check,                           name='health-check'),

    # Auth
    path('auth/register/',         views.UserRegistrationView.as_view(),  name='register'),
    path('auth/login/',            views.CustomLoginView.as_view(),        name='login'),
    path('auth/teacher/create/',   views.create_teacher,                   name='create-teacher'),

    # Profile
    path('me/',                    views.my_profile,                       name='my-profile'),

    # Friends
    path('friends/',                                        views.friends_list,            name='friends-list'),
    path('friends/requests/',                               views.friend_requests_list,    name='friend-requests-list'),
    path('friends/request/',                                views.send_friend_request,     name='send-friend-request'),
    path('friends/requests/<str:req_id>/accept/',           views.accept_friend_request,   name='accept-friend-request'),
    path('friends/requests/<str:req_id>/decline/',          views.decline_friend_request,  name='decline-friend-request'),

    # Classrooms
    path('classrooms/',                                     views.classrooms,             name='classrooms'),
    path('classrooms/my/',                                  views.my_classrooms,          name='my-classrooms'),
    path('classrooms/join/',                                views.join_classroom,         name='join-classroom'),
    path('classrooms/<str:classroom_id>/',                  views.classroom_detail,       name='classroom-detail'),
    path('classrooms/<str:classroom_id>/students/',         views.add_student_by_username, name='add-student'),
    path('classrooms/<str:classroom_id>/students/<str:student_id>/', views.remove_student, name='remove-student'),
    path('classrooms/<str:classroom_id>/announcements/',    views.post_announcement,      name='post-announcement'),
    path('classrooms/<str:classroom_id>/announcements/<int:ann_index>/', views.delete_announcement, name='delete-announcement'),
    path('classrooms/<str:classroom_id>/tickets/',          views.tickets,                name='tickets'),

    # Battle
    path('battle/scout/',          views.scout_match,                      name='scout-match'),

    # Classrooms — public auto-join
    path('classrooms/<str:classroom_id>/join-public/', views.join_public_classroom, name='join-public'),

    # Submissions & code execution
    path('tasks/<str:task_id>/submissions/', views.task_submissions,  name='task-submissions'),
    path('tasks/<str:task_id>/run/',         views.run_code,           name='run-code'),
    path('tasks/<str:task_id>/submit/',      views.record_submission,  name='record-submission'),
    path('tasks/<str:task_id>/unsubmit/',    views.unsubmit,           name='unsubmit'),

    # Admin
    path('admin/users/',                          views.admin_users,            name='admin-users'),
    path('admin/users/<str:user_id>/',            views.admin_user_action,      name='admin-user-action'),
    path('admin/classrooms/',                     views.admin_classrooms,       name='admin-classrooms'),
    path('admin/classrooms/<str:classroom_id>/',  views.admin_classroom_action, name='admin-classroom-action'),
    path('admin/tickets/',                        views.admin_tickets,          name='admin-tickets'),
    path('admin/tickets/<str:ticket_id>/',        views.admin_ticket_action,    name='admin-ticket-action'),
    path('admin/announcements/',                  views.admin_announcements,    name='admin-announcements'),
    path('admin/announcements/<str:aid>/',        views.admin_announcement_action, name='admin-announcements-action'),
    path('admin/logs/',                           views.admin_logs,             name='admin-logs'),

    # Public announcements (for students/teachers bell icon)
    path('announcements/',                        views.public_announcements,   name='public-announcements'),

    # Teacher raises ticket
    path('tickets/raise/',                        views.raise_ticket,           name='raise-ticket'),
    path('tickets/<str:ticket_id>/',              views.teacher_delete_ticket,  name='teacher-delete-ticket'),

    # Manual grading
    path('tasks/<str:task_id>/grade/',            views.grade_submission,        name='grade-submission'),

    # Per-user notifications (grading review, marks assigned)
    path('user-notifications/',                   views.user_notifications,          name='user-notifications'),
    path('user-notifications/<str:notif_id>/read/', views.mark_notification_read,   name='mark-notification-read'),
]
