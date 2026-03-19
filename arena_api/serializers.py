from rest_framework import serializers
from django.contrib.auth.models import User
from .models import CodingTask, Classroom, CoderProfile, TestCase, Submission, TECH_STACKS


class TestCaseSerializer(serializers.Serializer):
    input_data  = serializers.CharField()
    output_data = serializers.CharField()
    is_hidden   = serializers.BooleanField(default=False)


class SubmissionSerializer(serializers.Serializer):
    user_id        = serializers.CharField()
    username       = serializers.CharField()
    code           = serializers.CharField()
    passed         = serializers.BooleanField(default=False)
    output         = serializers.CharField(default='', allow_blank=True)
    language       = serializers.CharField(default='Python')
    score          = serializers.FloatField(default=0.0)
    marks_obtained = serializers.FloatField(default=0.0)
    grade          = serializers.CharField(default='', allow_blank=True)
    remarks        = serializers.CharField(default='', allow_blank=True)
    is_active      = serializers.BooleanField(default=True)
    status         = serializers.ChoiceField(choices=['Submitted', 'Unsubmitted'], default='Submitted')
    review_status  = serializers.ChoiceField(choices=['pending', 'graded'], default='graded')
    run_results    = serializers.ListField(child=serializers.DictField(), default=[])
    last_edited_at = serializers.DateTimeField(read_only=True)
    created_at     = serializers.DateTimeField(read_only=True)


class CodingTaskSerializer(serializers.Serializer):
    id            = serializers.SerializerMethodField()
    title         = serializers.CharField(max_length=200)
    description   = serializers.CharField()
    difficulty    = serializers.ChoiceField(choices=["Easy", "Medium", "Hard"], default="Easy")
    tech_stack    = serializers.ChoiceField(choices=TECH_STACKS, default="General")
    test_cases    = TestCaseSerializer(many=True, default=[])
    submissions   = SubmissionSerializer(many=True, read_only=True)
    due_date      = serializers.DateTimeField(required=False, allow_null=True)
    task_type     = serializers.ChoiceField(choices=["Mandatory", "CP"], default="Mandatory")
    content_type  = serializers.ChoiceField(choices=["Assignment", "Text", "Video", "VideoText"], default="Assignment")
    text_content  = serializers.CharField(default="", allow_blank=True)
    video_url     = serializers.CharField(default="", allow_blank=True)
    classroom_id  = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_final      = serializers.BooleanField(default=False)
    lab_number    = serializers.IntegerField(default=0)
    linked_lab    = serializers.IntegerField(default=0)
    hints         = serializers.ListField(child=serializers.CharField(), default=[])
    grading_mode  = serializers.ChoiceField(choices=["Percentage", "Marks", "Grade"], default="Percentage")
    grading_type  = serializers.ChoiceField(choices=["auto", "manual"], default="auto")
    allow_tab_completion = serializers.BooleanField(default=True)
    max_marks     = serializers.FloatField(default=100.0)
    pass_criteria = serializers.FloatField(default=50.0)
    allow_copy_paste = serializers.BooleanField(default=True)
    created_at    = serializers.DateTimeField(read_only=True)
    classroom_name = serializers.SerializerMethodField()
    classroom_type = serializers.SerializerMethodField()

    def get_classroom_name(self, obj):
        if not obj.classroom_id: return ''
        try:
            c = Classroom.objects.get(id=obj.classroom_id)
            return c.name
        except: return ''

    def get_classroom_type(self, obj):
        if not obj.classroom_id: return 'Public'
        try:
            c = Classroom.objects.get(id=obj.classroom_id)
            return c.type
        except: return 'Public'

    def get_id(self, obj):
        return str(obj.id)

    def create(self, validated_data):
        test_cases_data = validated_data.pop('test_cases', [])
        validated_data.pop('submissions', None)
        task = CodingTask(**validated_data)
        task.test_cases = [TestCase(**tc) for tc in test_cases_data]
        task.save()
        return task

    def update(self, instance, validated_data):
        test_cases_data = validated_data.pop('test_cases', None)
        validated_data.pop('submissions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if test_cases_data is not None:
            instance.test_cases = [TestCase(**tc) for tc in test_cases_data]
        instance.save()
        return instance


class CoderProfileSerializer(serializers.Serializer):
    id      = serializers.SerializerMethodField()
    user_id = serializers.CharField()
    level   = serializers.IntegerField(default=1)
    xp      = serializers.IntegerField(default=0)
    wins    = serializers.IntegerField(default=0)
    losses  = serializers.IntegerField(default=0)
    badges  = serializers.ListField(child=serializers.CharField(), default=[])
    rank    = serializers.CharField(default='Novice')
    role    = serializers.CharField(default='STUDENT')
    full_name = serializers.CharField(default='', allow_blank=True)
    reg_no  = serializers.CharField(default='', allow_blank=True)
    age     = serializers.IntegerField(default=0)
    gender  = serializers.CharField(default='')
    streak  = serializers.IntegerField(default=0)
    daily_activity = serializers.DictField(default={}, read_only=True)

    def get_id(self, obj):
        return str(obj.id)


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model  = User
        fields = ('username', 'email', 'password')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password']
        )
        CoderProfile(user_id=str(user.id), role='STUDENT').save()
        return user
