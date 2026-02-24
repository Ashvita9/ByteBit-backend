import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth.models import User
from arena_api.models import Classroom, CodingTask, TestCase

admin_user = User.objects.filter(is_superuser=True).first()
if not admin_user:
    print("No admin user found. Did you run createsuperuser?")
    # Fallback to id=1
    admin_id = 1
else:
    admin_id = admin_user.id

print(f"Using Admin ID: {admin_id}")

def create_track(name, tech_stack, num_tasks=10):
    c = Classroom.objects(name=name).first()
    if not c:
        c = Classroom(name=name, code=name.upper()[:6].replace(' ', '').replace('&', ''), type="Public", teacher_id=admin_id)
        c.save()
        print(f"Created Classroom: {name}")
    else:
        print(f"Classroom {name} already exists.")

    tasks_added = 0
    js_titles = ["Hello World in JS", "Basic Math", "Variables", "If Statements", "For Loops", "Functions", "Arrays", "Objects", "Array Methods", "Classes"]
    html_titles = ["Hello World HTML", "Headings", "Paragraphs", "Links", "Images", "Lists", "Tables", "Forms", "Divs and Spans", "Semantic HTML"]

    for i in range(1, num_tasks + 1):
        if tech_stack == "JavaScript":
            title = f"{tech_stack} Challenge #{i}: {js_titles[i-1]}"
            desc = f"Welcome to {title}. Write JavaScript code that prints the expected output. Use console.log()."
            tests = [
                TestCase(input_data="", output_data=f"js_result_test_{i}", is_hidden=False),
                TestCase(input_data="", output_data=f"js_hidden_{i}", is_hidden=True),
            ]
        else: # HTML
            title = f"{tech_stack} Challenge #{i}: {html_titles[i-1]}"
            desc = f"Welcome to {title}. Write HTML code that includes the requested elements."
            target_tag = ["<html>", "<h1>", "<p>", "<a>", "<img>", "<ul>", "<table>", "<form>", "<div>", "<article>"][i-1]
            tests = [
                TestCase(input_data="", output_data=target_tag, is_hidden=False),
            ]
            
        existing = CodingTask.objects(title=title, classroom_id=str(c.id)).first()
        if existing:
            if str(existing.id) not in c.task_ids:
                c.task_ids.append(str(existing.id))
            continue
            
        t = CodingTask(
            title=title,
            tech_stack=tech_stack,
            difficulty="Easy" if i <= 3 else "Medium" if i <= 7 else "Hard",
            description=desc,
            classroom_id=str(c.id),
            test_cases=tests,
            due_date=None
        )
        t.save()
        c.task_ids.append(str(t.id))
        tasks_added += 1
        print(f"Created task: {title}")
    
    c.save()
    print(f"Finished {name}, added {tasks_added} new tasks.")


# Drop old public tasks so we can re-create them properly
for c in Classroom.objects(type="Public"):
    for tid in c.task_ids:
        CodingTask.objects(id=tid).delete()
    c.task_ids = []
    c.save()

create_track("JavaScript Masterclass", "JavaScript")
create_track("HTML Builders", "HTML")
print("Done seeding public tracks.")
