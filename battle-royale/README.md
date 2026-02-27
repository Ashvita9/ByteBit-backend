# ⚔️ ByteBit Battle Royale — Backend

A real-time 1v1 elimination-based Battle Royale coding tournament service built with **Node.js**, **Express**, **Socket.io**, **Redis**, and **PostgreSQL**.

---

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Database Schema](#database-schema)
- [REST API Endpoints](#rest-api-endpoints)
- [Socket.io Event Map](#socketio-event-map)
- [Redis Usage](#redis-usage)
- [Tournament Flow](#tournament-flow)
- [Frontend Integration Guide](#frontend-integration-guide)

---

## Architecture Overview

```
┌──────────────┐    REST     ┌──────────────────────────────────────────┐
│   Frontend   │────────────▶│  Express Server (port 4000)             │
│  (React/Vue) │◀───────────▶│                                        │
│              │  Socket.io  │  ┌──────────┐  ┌─────────────────────┐ │
└──────────────┘             │  │  Routes   │  │  Socket Handlers    │ │
                             │  │  /royale  │  │  room / match /     │ │
                             │  │  /match   │  │  admin               │ │
                             │  │  /leader  │  └────────┬────────────┘ │
                             │  └────┬─────┘           │              │
                             │       │                  │              │
                             │  ┌────▼──────────────────▼────────┐    │
                             │  │         Services Layer          │    │
                             │  │  tournament · match · codeRunner│    │
                             │  │  aiEvaluator                    │    │
                             │  └────┬──────────────────┬────────┘    │
                             │       │                  │              │
                             │  ┌────▼─────┐     ┌─────▼──────┐      │
                             │  │PostgreSQL │     │   Redis     │      │
                             │  │(persist)  │     │ (live state)│      │
                             │  └──────────┘     └────────────┘      │
                             └──────────────────────────────────────────┘
```

This service runs **alongside** the existing Django backend. Users authenticate via the Django JWT flow; this service validates the same tokens.

---

## Quick Start

### Prerequisites

- **Node.js** ≥ 18
- **PostgreSQL** ≥ 14
- **Redis** ≥ 6

### 1. Install Dependencies

```bash
cd battle-royale
npm install
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL, Redis, and JWT config
```

### 3. Run Database Migrations

```bash
npm run migrate
```

### 4. Start the Server

```bash
# Development (with auto-reload)
npm run dev

# Production
npm start
```

Server boots on `http://localhost:4000` with output:
```
✅ PostgreSQL connected
✅ Redis connected
🚀 Battle Royale server on port 4000
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PORT` | No | `4000` | HTTP server port |
| `NODE_ENV` | No | `development` | `development` or `production` |
| `DATABASE_URL` | **Yes** | — | PostgreSQL connection string |
| `REDIS_URL` | **Yes** | — | Redis connection URL |
| `JWT_SECRET` | **Yes** | — | Must match your Django backend's `SECRET_KEY` |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `DEFAULT_MAX_PLAYERS` | No | `10` | Max players per tournament |
| `ROUND_COUNTDOWN_SECONDS` | No | `5` | Countdown before tournament starts |
| `MATCH_TIMEOUT_SECONDS` | No | `600` | Max time per match (10 min) |
| `CODE_EXECUTION_TIMEOUT_MS` | No | `10000` | Code execution timeout |
| `CORS_ORIGIN` | No | `*` | Allowed CORS origins (comma-separated) |

---

## Database Schema

### Tables

```
battle_royales                    battle_royale_participants
┌──────────────────────┐         ┌──────────────────────────┐
│ id (UUID, PK)        │◀───────│ royale_id (FK)           │
│ code (unique)        │         │ user_id                  │
│ title                │         │ username                 │
│ created_by           │         │ role                     │
│ difficulty           │         │ eliminated_in_round      │
│ type (public/private)│         │ is_connected             │
│ status               │         │ UNIQUE(royale_id,user_id)│
│ max_players          │         └──────────────────────────┘
│ current_round        │
│ total_rounds         │         matches
│ winner_id            │         ┌──────────────────────────┐
└──────────────────────┘    ┌───│ royale_id (FK)           │
                            │   │ round_number             │
    submissions             │   │ match_index              │
    ┌───────────────────┐   │   │ player1_id / player2_id  │
    │ match_id (FK) ────┼───┘   │ winner_id                │
    │ user_id           │       │ question_* (snapshot)     │
    │ code              │       │ test_cases (JSONB)        │
    │ language          │       │ status                   │
    │ passed            │       └──────────────────────────┘
    │ time_taken_ms     │
    │ time_complexity   │       battle_royale_points
    │ UNIQUE(match,user)│       ┌──────────────────────────┐
    └───────────────────┘       │ user_id (unique)         │
                                │ points, wins, losses     │
                                │ tournaments_played       │
                                └──────────────────────────┘
```

---

## REST API Endpoints

### Authentication
All endpoints require `Authorization: Bearer <JWT>` header.

### Endpoints

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/health` | — | Health check (no auth) |
| `POST` | `/api/royale` | ADMIN, TEACHER | Create a Battle Royale |
| `GET` | `/api/royale/:id` | Any | Get royale details + bracket |
| `POST` | `/api/royale/join` | Any | Join by room code |
| `POST` | `/api/royale/:id/start` | ADMIN, TEACHER | Force-start tournament |
| `POST` | `/api/match/:id/submit` | Any (participant) | Submit code solution |
| `GET` | `/api/leaderboard` | Any | Points ranking |
| `GET` | `/api/leaderboard/:userId` | Any | User's BR stats |

### Example: Create a Battle Royale

```bash
curl -X POST http://localhost:4000/api/royale \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Weekly Challenge",
    "difficulty": "Medium",
    "maxPlayers": 8
  }'

# Response:
# {
#   "message": "Battle Royale created",
#   "royale": {
#     "id": "uuid...",
#     "code": "XK7P3N",
#     "title": "Weekly Challenge",
#     ...
#   }
# }
```

### Example: Join by Code

```bash
curl -X POST http://localhost:4000/api/royale/join \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"code": "XK7P3N"}'
```

---

## Socket.io Event Map

### Connection

```javascript
import { io } from 'socket.io-client';

const socket = io('http://localhost:4000', {
  auth: { token: '<JWT_TOKEN>' }
});
```

### Event Diagram

```
 CLIENT → SERVER                         SERVER → CLIENT
 ─────────────────                       ─────────────────

 royale:join { code }               ──▶  royale:player_joined { user, playerCount, maxPlayers }
 royale:leave                       ──▶  royale:player_left   { user, playerCount }
                                    ──▶  royale:countdown     { seconds }
                                    ──▶  royale:starting      { bracket, totalRounds }

 match:submit { matchId,            ──▶  match:started        { matchId, roundNumber, opponent,
               code, language }                                  question, isFinal }
                                    ──▶  match:submission_ack { matchId, passed, output,
                                                                passedCount, totalCount }
                                    ──▶  match:opponent_progress { matchId, percentage }
                                    ──▶  match:result         { matchId, winner, loser }

                                    ──▶  round:advance        { round, isFinal, matches }
                                    ──▶  tournament:complete  { winner, pointsAwarded }
                                    ──▶  tournament:eliminated { round, defeatedBy }

 admin:start  { royaleId }          ──▶  (triggers countdown + start)
 admin:kick   { royaleId, userId }  ──▶  (removes player, emits player_left)
                                    ──▶  error                { message }
```

### Client-Side Event Handling

```javascript
// Join a room
socket.emit('royale:join', { code: 'XK7P3N' });

// Listen for match start
socket.on('match:started', ({ matchId, opponent, question }) => {
  console.log(`Match vs ${opponent.username}`);
  console.log(`Question: ${question.title}`);
  // Show coding editor
});

// Submit solution
socket.emit('match:submit', {
  matchId: 'uuid...',
  code: 'print(input_data[::-1])',
  language: 'Python'
});

// Listen for results
socket.on('match:submission_ack', ({ passed, output }) => {
  console.log(passed ? '✅ Correct!' : `❌ ${output}`);
});

socket.on('match:result', ({ winner }) => {
  console.log(`Winner: ${winner.username}`);
});

socket.on('tournament:complete', ({ winner, pointsAwarded }) => {
  console.log(`🏆 Champion: ${winner.username} (+${pointsAwarded} pts)`);
});

socket.on('tournament:eliminated', ({ round, defeatedBy }) => {
  console.log(`💀 Eliminated in round ${round} by ${defeatedBy}`);
});
```

---

## Redis Usage

| Key Pattern | Type | TTL | Purpose |
|---|---|---|---|
| `royale:{id}:state` | Hash | 2h | Tournament status, player count, current round |
| `royale:{id}:players` | Set | 2h | Connected player user IDs |
| `royale:{id}:bracket` | String (JSON) | 2h | Live bracket structure |
| `royale:{id}:usedQuestions` | String (JSON) | 2h | Question IDs already assigned |
| `royale:{id}:lock` | String | 30s | Distributed lock for state transitions |
| `match:{id}:state` | Hash | 2h | Active match state (start time, submission count, isFinal) |
| `user:{id}:socket` | String | 2h | Socket ID → prevents duplicate connections |

All keys auto-expire. Tournament cleanup also runs 30s after completion.

---

## Tournament Flow

```
1. TEACHER/ADMIN creates Battle Royale       →  POST /api/royale
                                                 Returns { code: "XK7P3N" }

2. Students join via code                     →  socket.emit('royale:join', { code })
                                                 All receive: royale:player_joined

3. Room fills (or admin force-starts)         →  royale:countdown { 5, 4, 3, 2, 1 }
                                                 royale:starting { bracket }

4. Round 1 matches fire                       →  Each pair gets: match:started
                                                 { matchId, opponent, question }

5. Players code and submit                    →  socket.emit('match:submit', { code })
                                                 Submitter: match:submission_ack
                                                 Opponent: match:opponent_progress

6. First valid solution wins (normal rounds)  →  match:result { winner, loser }
                                                 Losers: tournament:eliminated

7. All round matches complete                 →  round:advance { nextRound, matches }
                                                 Winners get new match:started

8. Final round: BOTH must submit              →  Compare: time → AI complexity
                                                 match:result { winner }

9. Champion crowned                           →  tournament:complete { winner, points }
                                                 +100 Battle Royale Points
```

### Bracket Example (8 players)

```
Round 1 (4 matches)          Round 2 (2 matches)        Final
┌─────────────────┐
│ Player A        │──┐
│ Player B        │  ├──▶ Winner 1 ──┐
└─────────────────┘  │               │
┌─────────────────┐  │               ├──▶ Winner 3 ──┐
│ Player C        │──┘               │               │
│ Player D        │                  │               │
└─────────────────┘                  │               ├──▶ 🏆 CHAMPION
┌─────────────────┐                  │               │
│ Player E        │──┐               │               │
│ Player F        │  ├──▶ Winner 2 ──┘               │
└─────────────────┘  │                               │
┌─────────────────┐  │                               │
│ Player G        │──┘                               │
│ Player H        │           ──▶ Winner 4 ──────────┘
└─────────────────┘
```

---

## Frontend Integration Guide

### 1. Connect to Both Backends

```javascript
// Existing Django API (auth, classrooms, tasks)
const API_URL = 'https://your-django-backend.com/api';

// Battle Royale service
const BR_URL = 'http://localhost:4000';
const BR_API = `${BR_URL}/api`;
const socket = io(BR_URL, { auth: { token: jwtToken } });
```

### 2. Typical User Flow

```
Login (Django)  →  Get JWT  →  Create/Join Royale (BR API)  →  Connect Socket
     │                              │                              │
     ▼                              ▼                              ▼
 Dashboard           Room Code: XK7P3N              Waiting Room (live)
                                                           │
                                                    Match Started
                                                           │
                                                    Code Editor + Timer
                                                           │
                                                    Submit Solution
                                                           │
                                                  Win → Next Round
                                                  Lose → Spectate
                                                           │
                                                    🏆 Champion!
```

### 3. Required Socket Events to Handle

| Event | Action |
|---|---|
| `royale:player_joined` | Update player list in waiting room |
| `royale:countdown` | Show countdown overlay |
| `royale:starting` | Render bracket visualization |
| `match:started` | Show code editor + question |
| `match:submission_ack` | Show pass/fail feedback |
| `match:opponent_progress` | Update opponent progress bar |
| `match:result` | Show match winner |
| `round:advance` | Update bracket, prepare next match |
| `tournament:complete` | Show champion screen |
| `tournament:eliminated` | Show elimination screen |
| `error` | Display error toast |

---

## File Structure

```
battle-royale/
├── package.json
├── .env.example
├── knexfile.js
├── src/
│   ├── index.js                    ← Server entry point
│   ├── config/index.js             ← Environment config
│   ├── db/
│   │   ├── knex.js                 ← DB connection
│   │   └── migrations/001_initial.js
│   ├── middleware/
│   │   ├── auth.js                 ← JWT verification
│   │   └── roles.js                ← Role-based access
│   ├── routes/
│   │   ├── royale.js               ← Tournament CRUD
│   │   ├── match.js                ← Code submission
│   │   └── leaderboard.js          ← Points ranking
│   ├── services/
│   │   ├── tournamentService.js    ← Core tournament logic
│   │   ├── matchService.js         ← Match lifecycle
│   │   ├── codeRunner.js           ← Sandboxed code exec
│   │   └── aiEvaluator.js          ← Complexity analysis
│   ├── socket/
│   │   ├── index.js                ← Socket.io init
│   │   ├── events.js               ← Event constants
│   │   └── handlers/
│   │       ├── roomHandler.js      ← Join/leave room
│   │       ├── matchHandler.js     ← Code submissions
│   │       └── adminHandler.js     ← Force start/kick
│   └── utils/
│       ├── bracketGenerator.js     ← Tournament brackets
│       ├── codeGenerator.js        ← Room codes
│       └── redis.js                ← Redis client
└── README.md
```
