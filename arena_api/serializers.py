from rest_framework_mongoengine import serializers as mongoserializers
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import CodingTask, CoderProfile, TestCase, Submission


class TestCaseSerializer(mongoserializers.EmbeddedDocumentSerializer):
    class Meta:
        model = TestCase
        fields = '__all__'


class SubmissionSerializer(mongoserializers.EmbeddedDocumentSerializer):
    class Meta:
        model = Submission
        fields = '__all__'


class CodingTaskSerializer(mongoserializers.DocumentSerializer):
    test_cases  = TestCaseSerializer(many=True)
    submissions = SubmissionSerializer(many=True, read_only=True)

    class Meta:
        model  = CodingTask
        fields = '__all__'

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


class CoderProfileSerializer(mongoserializers.DocumentSerializer):
    class Meta:
        model  = CoderProfile
        fields = '__all__'


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
        CoderProfile(user_id=user.id, role='STUDENT').save()
        return user
