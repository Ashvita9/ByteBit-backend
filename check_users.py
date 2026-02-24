import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth.models import User

print("--- Registered Users ---")
for user in User.objects.all():
    print(f"ID: {user.id} | Username: '{user.username}' | Email: '{user.email}' | Is Active: {user.is_active}")
