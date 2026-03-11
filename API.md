# ByteBit API Reference

**Base URL:** `https://bytebitsbackend.duckdns.org/api`  
**Auth:** JWT Bearer token — include `Authorization: Bearer <access_token>` on protected routes.

---

## Health

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/health/` | None |

```bash
curl https://bytebitsbackend.duckdns.org/api/health/
```

---

## Auth

### Register
`POST /api/auth/register/`

```json
// Request
{
  "username": "john",
  "email": "john@example.com",
  "password": "secret123"
}

// Response 201
{
  "id": "...",
  "username": "john",
  "email": "john@example.com"
}
```

### Login
`POST /api/auth/login/`

```json
// Request
{
  "username": "john",
  "password": "secret123"
}

// Response 200
{
  "access": "<jwt_access_token>",
  "refresh": "<jwt_refresh_token>"
}
```

### Create Teacher Account *(Admin only)*
`POST /api/auth/teacher/create/`

```json
// Request
{
  "username": "ms_smith",
  "email": "smith@school.com",
  "password": "secret123"
}
```

---

## Profile

### Get My Profile
`GET /api/me/` — *User*

```json
// Response 200
{
  "username": "john",
  "email": "john@example.com",
  "role": "student",
  "xp": 320
}
```

---

## Tasks

Tasks are managed via a REST viewset at `/api/tasks/`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/tasks/` | None | List all tasks |
| POST | `/api/tasks/` | Teacher | Create a task |
| GET | `/api/tasks/<id>/` | None | Get task detail |
| PUT | `/api/tasks/<id>/` | Teacher | Update task |
| DELETE | `/api/tasks/<id>/` | Teacher | Delete task |
| GET | `/api/tasks/<id>/submissions/` | User | List submissions for task |
| POST | `/api/tasks/<id>/run/` | User | Run code (test only) |
| POST | `/api/tasks/<id>/submit/` | User | Submit solution |
| POST | `/api/tasks/<id>/unsubmit/` | User | Retract submission |

### Run Code
`POST /api/tasks/<id>/run/`

```json
// Request
{
  "code": "print('hello')",
  "language": "python"
}

// Response 200
{
  "stdout": "hello\n",
  "stderr": "",
  "passed": true
}
```

### Submit Solution
`POST /api/tasks/<id>/submit/`

```json
// Request
{
  "code": "print('hello')",
  "language": "python"
}

// Response 200
{
  "status": "accepted",
  "xp_earned": 50
}
```

---

## Classrooms

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET / POST | `/api/classrooms/` | Teacher (POST) | List or create classrooms |
| GET | `/api/classrooms/my/` | User | Classrooms I belong to |
| POST | `/api/classrooms/join/` | User | Join via code |
| GET / PATCH / DELETE | `/api/classrooms/<id>/` | Teacher | Classroom detail |
| POST | `/api/classrooms/<id>/students/` | Teacher | Add student by username |
| DELETE | `/api/classrooms/<id>/students/<student_id>/` | Teacher | Remove student |
| POST | `/api/classrooms/<id>/announcements/` | Teacher | Post announcement |
| GET / POST | `/api/classrooms/<id>/tickets/` | User | View / raise tickets |
| POST | `/api/classrooms/<id>/join-public/` | User | Join public classroom |

### Join Classroom
`POST /api/classrooms/join/`

```json
// Request
{ "code": "ABC123" }

// Response 200
{ "detail": "Joined classroom." }
```

---

## Battle

### Scout a Match
`POST /api/battle/scout/`

```json
// Request — no body required

// Response 200
{
  "room_id": "...",
  "task": { "id": "...", "title": "Two Sum" },
  "opponent": "alice"
}
```

---

## Announcements

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/announcements/` | User | Global announcements (bell icon) |
| POST | `/api/tickets/raise/` | Teacher | Raise a support ticket |

---

## Admin

All `/api/admin/*` routes require a superuser account.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/users/` | List all users |
| PATCH / DELETE | `/api/admin/users/<id>/` | Edit or delete user |
| GET | `/api/admin/classrooms/` | List all classrooms |
| PATCH / DELETE | `/api/admin/classrooms/<id>/` | Edit or delete classroom |
| GET | `/api/admin/tickets/` | List all tickets |
| PATCH | `/api/admin/tickets/<id>/` | Update ticket status |
| GET / POST | `/api/admin/announcements/` | Manage global announcements |
| GET | `/api/admin/logs/` | Action audit log |

---

## WebSocket

Connect to `wss://bytebitsbackend.duckdns.org/ws/arena/<room_id>/` with a valid JWT.

```js
const ws = new WebSocket('wss://bytebitsbackend.duckdns.org/ws/arena/ROOM_ID/');
ws.onopen = () => ws.send(JSON.stringify({ type: 'join', token: '<access_token>' }));
```

---

## Error Responses

| Code | Meaning |
|------|---------|
| 400 | Bad request / validation error |
| 401 | Missing or invalid JWT |
| 403 | Insufficient permissions |
| 404 | Resource not found |
| 500 | Server error |

```json
// Example 401
{ "detail": "Authentication credentials were not provided." }
```
