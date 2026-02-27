from mongoengine import Document, EmbeddedDocument, fields
from django.contrib.auth.models import User
from datetime import datetime
import random, string

TECH_STACKS = ["Python", "JavaScript", "C++", "Java", "SQL", "TypeScript", "Go", "HTML", "General"]


def gen_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ── Profiles ───────────────────────────────────────────────────────────────────

class CoderProfile(Document):
    user_id = fields.StringField(required=True, unique=True)

    level      = fields.IntField(default=1)
    xp         = fields.IntField(default=0)
    wins       = fields.IntField(default=0)
    losses     = fields.IntField(default=0)
    badges     = fields.ListField(fields.StringField(), default=[])
    rank       = fields.StringField(
        default="Novice",
        choices=["Novice", "Apprentice", "Warrior", "Elite", "Grandmaster", "Not Applicable"]
    )
    role       = fields.StringField(default="STUDENT", choices=["ADMIN", "TEACHER", "STUDENT"])

    meta = {'collection': 'coder_profiles'}

    def __str__(self):
        try:
            return User.objects.get(id=self.user_id).username
        except User.DoesNotExist:
            return f"User ID: {self.user_id}"

    def recalc_rank(self):
        """Only meaningful for students — teachers don't earn XP."""
        if self.xp >= 2000:   self.rank = "Grandmaster"
        elif self.xp >= 1000: self.rank = "Elite"
        elif self.xp >= 500:  self.rank = "Warrior"
        elif self.xp >= 200:  self.rank = "Apprentice"
        else:                 self.rank = "Novice"


# ── Coding Tasks ───────────────────────────────────────────────────────────────

class TestCase(EmbeddedDocument):
    input_data  = fields.StringField(required=True)
    output_data = fields.StringField(required=True)
    is_hidden   = fields.BooleanField(default=False)


class Submission(EmbeddedDocument):
    user_id      = fields.StringField(required=True)
    username     = fields.StringField(required=True)
    code         = fields.StringField(required=True)
    passed       = fields.BooleanField(default=False)
    output       = fields.StringField(default='')
    language     = fields.StringField(default='Python')
    # Raw score (percentage 0-100 of test cases passed)
    score        = fields.FloatField(default=0.0)
    # Marks-based grading (computed from score + task grading config)
    marks_obtained = fields.FloatField(default=0.0)
    grade          = fields.StringField(default='')
    remarks      = fields.StringField(default='')
    # Versioning
    is_active    = fields.BooleanField(default=True)
    status       = fields.StringField(default='Submitted', choices=['Submitted', 'Unsubmitted'])
    last_edited_at = fields.DateTimeField(default=datetime.utcnow)
    created_at   = fields.DateTimeField(default=datetime.utcnow)


class CodingTask(Document):
    title         = fields.StringField(max_length=200, required=True)
    description   = fields.StringField(required=True)
    difficulty    = fields.StringField(choices=["Easy", "Medium", "Hard"], default="Easy")
    tech_stack    = fields.StringField(choices=TECH_STACKS, default="General")
    test_cases    = fields.ListField(fields.EmbeddedDocumentField(TestCase))
    submissions   = fields.ListField(fields.EmbeddedDocumentField(Submission), default=[])
    due_date      = fields.DateTimeField(required=False)
    task_type     = fields.StringField(choices=["Mandatory", "CP"], default="Mandatory")
    classroom_id  = fields.StringField(required=False)
    is_final      = fields.BooleanField(default=False)
    hints         = fields.ListField(fields.StringField(), default=[])
    # Grading configuration set by teacher
    grading_mode  = fields.StringField(choices=["Percentage", "Marks", "Grade"], default="Percentage")
    max_marks     = fields.FloatField(default=100.0)
    pass_criteria = fields.FloatField(default=50.0)   # % or marks needed to pass
    created_at    = fields.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'coding_tasks', 'ordering': ['-created_at']}

    def __str__(self):
        return self.title

    def compute_grade(self, score_pct):
        """Return letter grade for a score percentage."""
        if score_pct >= 90:  return 'A+'
        if score_pct >= 80:  return 'A'
        if score_pct >= 70:  return 'B'
        if score_pct >= 60:  return 'C'
        if score_pct >= 50:  return 'D'
        return 'F'


# ── Classroom ──────────────────────────────────────────────────────────────────

class Announcement(EmbeddedDocument):
    message    = fields.StringField(required=True)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    pinned     = fields.BooleanField(default=False)


class Classroom(Document):
    name        = fields.StringField(max_length=200, required=True)
    code        = fields.StringField(required=True)
    type        = fields.StringField(choices=["Public", "Private"], default="Public")
    teacher_id  = fields.StringField(required=True)
    student_ids = fields.ListField(fields.StringField(), default=[])
    task_ids    = fields.ListField(fields.StringField(), default=[])
    is_locked   = fields.BooleanField(default=False)
    announcements = fields.ListField(fields.EmbeddedDocumentField(Announcement), default=[])
    created_at  = fields.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'classrooms', 'ordering': ['-created_at']}

    def __str__(self):
        return self.name


# ── Global Announcements / Broadcasts ──────────────────────────────────────────

class GlobalAnnouncement(Document):
    """Platform-wide broadcasts by admins targeting specific roles or everyone."""
    title       = fields.StringField(required=True, max_length=200)
    message     = fields.StringField(required=True)
    targetRole  = fields.StringField(choices=["ALL", "STUDENT", "TEACHER"], default="ALL")
    isPinned    = fields.BooleanField(default=False)
    created_at  = fields.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'global_announcements', 'ordering': ['-created_at']}


# ── Tickets ────────────────────────────────────────────────────────────────────


class Ticket(Document):
    """Teacher raises a ticket. Admin resolves it."""
    ticket_type    = fields.StringField(
        choices=["Revoke Credit", "Remove Student"],
        default="Revoke Credit"
    )
    raised_by_id      = fields.StringField(required=True)
    raised_by_username = fields.StringField(default='')
    student_id        = fields.StringField(required=True)
    student_username  = fields.StringField(default='')
    task_id           = fields.StringField(default='')
    task_title        = fields.StringField(default='')
    classroom_id      = fields.StringField(required=True)
    classroom_name    = fields.StringField(default='')
    reason            = fields.StringField(required=True)   # mandatory remarks
    status            = fields.StringField(choices=["Open", "Resolved"], default="Open")
    admin_note        = fields.StringField(default='')
    created_at        = fields.DateTimeField(default=datetime.utcnow)
    resolved_at       = fields.DateTimeField(required=False)

    meta = {'collection': 'tickets', 'ordering': ['-created_at']}


# ── Action Log ─────────────────────────────────────────────────────────────────

class ActionLog(Document):
    """Immutable log of every significant platform action."""
    action_type   = fields.StringField(required=True)  # e.g. 'submission', 'credit_revoked', ...
    actor_id      = fields.StringField(required=True)
    actor_username = fields.StringField(default='')
    target_user_id = fields.StringField(required=False)
    target_username = fields.StringField(default='')
    task_id       = fields.StringField(default='')
    task_title    = fields.StringField(default='')
    classroom_id  = fields.StringField(default='')
    classroom_name = fields.StringField(default='')
    details       = fields.StringField(default='')    # human-readable description
    created_at    = fields.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'action_logs', 'ordering': ['-created_at']}


# ── Battle Rooms ───────────────────────────────────────────────────────────────

class BattleRoom(Document):
    room_code  = fields.StringField(max_length=6, unique=True, required=True)
    task_id    = fields.StringField(required=True)
    player1_id = fields.StringField(required=False)
    player2_id = fields.StringField(required=False)
    winner_id  = fields.StringField(required=False)
    is_active  = fields.BooleanField(default=True)
    created_at = fields.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'battle_rooms'}

    def __str__(self):
        return f"Room {self.room_code}"