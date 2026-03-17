import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import CoderProfile, CodingTask, Submission, Tournament


class BattleConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_name       = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'battle_{self.room_name}'
        self.user            = self.scope.get('user')

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        if self.user and self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {'type': 'player_joined', 'username': self.user.username}
            )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data         = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'code_submit':
                await self.handle_code_submit(data)
            elif message_type == 'attack':
                await self.handle_attack(data)
            elif message_type == 'chat_message':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type':    'chat_message',
                        'message': data.get('message', ''),
                        'sender':  self.user.username if (self.user and self.user.is_authenticated) else 'Anonymous'
                    }
                )
        except Exception as e:
            await self.send(text_data=json.dumps({'type': 'error', 'message': str(e)}))

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def handle_code_submit(self, data):
        code     = data.get('code', '')
        task_id  = data.get('task_id')
        language = data.get('language', 'Python')

        passed, output = await self.run_code(code, task_id)

        username = self.user.username if (self.user and self.user.is_authenticated) else 'Anonymous'
        user_id  = self.user.id       if (self.user and self.user.is_authenticated) else 0

        # Persist submission
        await self.save_submission(task_id, user_id, username, code, passed, output, language)

        # Send result back to the submitter
        await self.send(text_data=json.dumps({
            'type':   'submission_result',
            'passed': passed,
            'output': output,
        }))

        # If solved → game over for the whole room
        if passed:
            if self.user and self.user.is_authenticated:
                await self.update_stats(self.user.id, won=True)
            await self.channel_layer.group_send(
                self.room_group_name,
                {'type': 'game_over', 'winner': username}
            )

    async def handle_attack(self, data):
        username = self.user.username if (self.user and self.user.is_authenticated) else 'Anonymous'
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type':        'attack_received',
                'attack_type': data.get('attack_type', 'blur'),
                'attacker':    username,
            }
        )

    # ── Group message event handlers ──────────────────────────────────────────

    async def player_joined(self, event):
        await self.send(text_data=json.dumps(event))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def attack_received(self, event):
        await self.send(text_data=json.dumps(event))

    async def game_over(self, event):
        await self.send(text_data=json.dumps(event))

    # ── DB helpers ────────────────────────────────────────────────────────────

    @database_sync_to_async
    def run_code(self, code, task_id):
        """Execute user code against all visible + hidden test cases."""
        import sys, io, textwrap
        try:
            task = CodingTask.objects.get(id=task_id)
        except Exception as e:
            return False, f'Task not found: {e}'

        for tc in task.test_cases:
            old_stdout = sys.stdout
            sys.stdout = buf = io.StringIO()
            try:
                cleaned    = textwrap.dedent(code)
                exec_code  = f"input_data = '{tc.input_data}'\n{cleaned}"
                exec(exec_code, {})
                got        = buf.getvalue().strip()
                expected   = tc.output_data.strip()
                if got != expected:
                    sys.stdout = old_stdout
                    return False, f"❌  Expected: {expected!r}\n   Got:      {got!r}"
            except Exception as e:
                sys.stdout = old_stdout
                return False, f'Runtime Error: {e}'
            finally:
                sys.stdout = old_stdout

        return True, '✅ All test cases passed!'

    @database_sync_to_async
    def save_submission(self, task_id, user_id, username, code, passed, output, language):
        try:
            task = CodingTask.objects.get(id=task_id)
            sub  = Submission(
                user_id  = user_id,
                username = username,
                code     = code,
                passed   = passed,
                output   = output,
                language = language,
            )
            task.submissions.append(sub)
            task.save()
        except Exception as e:
            print(f'Error saving submission: {e}')

    @database_sync_to_async
    def update_stats(self, user_id, won: bool):
        try:
            profile = CoderProfile.objects.get(user_id=user_id)
            if won:
                profile.wins += 1
                profile.xp   += 100
                # Award badges
                if profile.wins == 1  and '🏆 First Victory' not in profile.badges:
                    profile.badges.append('🏆 First Victory')
                if profile.wins == 5  and '⭐ 5-Win Streak'  not in profile.badges:
                    profile.badges.append('⭐ 5-Win Streak')
                if profile.wins == 10 and '💎 Legend'        not in profile.badges:
                    profile.badges.append('💎 Legend')
            else:
                profile.losses += 1
            profile.recalc_rank()
            profile.save()
        except Exception as e:
            print(f'Error updating stats: {e}')


# ── Tournament Consumer ────────────────────────────────────────────────────────

class TournamentConsumer(AsyncWebsocketConsumer):
    """
    WebSocket handler for a single tournament match.
    URL pattern: ws/tournament/<tournament_id>/match/<match_id>/
    Group name:  tournament_<tournament_id>_match_<match_id>

    Events accepted (client → server):
      { type: "join" }
      { type: "code_submit", code: "...", language: "python" }
      { type: "teacher_decide", winner_id: "..." }   (teacher only)

    Events broadcast (server → clients):
      { type: "question_data", question: {...} }
      { type: "players_ready", players: [...] }
      { type: "code_result", results: [...], passed: bool, userId: "..." }
      { type: "match_won", winnerId: "...", winnerUsername: "..." }
      { type: "error", message: "..." }
    """

    async def connect(self):
        self.tournament_id = self.scope['url_route']['kwargs']['tournament_id']
        self.match_id      = self.scope['url_route']['kwargs']['match_id']
        self.group_name    = f'tournament_{self.tournament_id}_match_{self.match_id}'
        self.user          = self.scope.get('user')

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        if self.user and self.user.is_authenticated:
            # Send question data to the newly connected player
            question, players = await self.get_match_context()
            if question:
                await self.send(text_data=json.dumps({
                    'type':     'question_data',
                    'question': question,
                }))
            else:
                await self.send(text_data=json.dumps({
                    'type':    'error',
                    'message': 'Failed to load question. Please contact support.',
                }))

            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'players_ready', 'players': players}
            )
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Authentication failed. Please refresh or login again.'
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data     = json.loads(text_data)
            msg_type = data.get('type')

            if msg_type == 'code_submit':
                await self.handle_code_submit(data)
            elif msg_type == 'teacher_decide':
                await self.handle_teacher_decide(data)
        except Exception as e:
            await self.send(text_data=json.dumps({'type': 'error', 'message': str(e)}))

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def handle_code_submit(self, data):
        code     = data.get('code', '')
        language = data.get('language', 'python')

        if not self.user or not self.user.is_authenticated:
            return

        results, passed = await self.run_code_against_match(code, language)

        # Broadcast result to both players
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type':    'code_result',
                'results': results,
                'passed':  passed,
                'userId':  str(self.user.id),
                'username': self.user.username,
            }
        )

        if passed:
            winner_id, winner_username = await self.mark_match_winner(str(self.user.id))
            if winner_id:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type':            'match_won',
                        'winnerId':        winner_id,
                        'winnerUsername':  winner_username,
                    }
                )

    async def handle_teacher_decide(self, data):
        """Teacher manually picks the winner of this match."""
        if not self.user or not self.user.is_authenticated:
            return
        winner_id = data.get('winner_id', '')
        if not winner_id:
            return

        winner_id, winner_username = await self.force_match_winner(winner_id)
        if winner_id:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type':           'match_won',
                    'winnerId':       winner_id,
                    'winnerUsername': winner_username,
                    'decidedByTeacher': True,
                }
            )

    # ── Group event handlers (channel layer → WebSocket) ─────────────────────

    async def players_ready(self, event):
        await self.send(text_data=json.dumps({
            'type':    'players_ready',
            'players': event['players'],
        }))

    async def code_result(self, event):
        await self.send(text_data=json.dumps({
            'type':     'code_result',
            'results':  event['results'],
            'passed':   event['passed'],
            'userId':   event['userId'],
            'username': event['username'],
        }))

    async def match_won(self, event):
        await self.send(text_data=json.dumps({
            'type':             'match_won',
            'winnerId':         event['winnerId'],
            'winnerUsername':   event['winnerUsername'],
            'decidedByTeacher': event.get('decidedByTeacher', False),
        }))

    # ── DB helpers ────────────────────────────────────────────────────────────

    @database_sync_to_async
    def get_match_context(self):
        """Return (question_dict, players_list) for this match."""
        try:
            t = Tournament.objects.get(id=self.tournament_id)
        except Exception:
            return None, []

        match = next((m for m in t.matches if m.match_id == self.match_id), None)
        if not match:
            print(f"Match {self.match_id} not found in tournament {self.tournament_id}")
            return None, []

        question = None
        if t.questions and match.question_index < len(t.questions):
            q = t.questions[match.question_index]
            question = {
                'title':       q.title,
                'description': q.description,
                'difficulty':  q.difficulty,
                'testCases': [
                    {'input': tc.input_data, 'expected_output': tc.output_data}
                    for tc in q.test_cases
                ],
            }
        else:
            print(f"Debug: Match {self.match_id} q_idx={match.question_index} out of range (len={len(t.questions)})")

        players = []
        usernames = dict(t.participant_usernames)
        for pid in [match.player1_id, match.player2_id]:
            if pid:
                players.append({'id': pid, 'username': usernames.get(pid, pid)})

        return question, players

    @database_sync_to_async
    def run_code_against_match(self, code, language):
        """Run code against the match question's test cases; return (results, all_passed)."""
        import subprocess, tempfile, os
        from .runner import run_test_cases  # Use shared runner

        try:
            t = Tournament.objects.get(id=self.tournament_id)
        except Exception:
            return [], False

        match = next((m for m in t.matches if m.match_id == self.match_id), None)
        if not match or not t.questions:
            return [], False

        q = t.questions[match.question_index] if match.question_index < len(t.questions) else None
        if not q:
            return [], False

        # Prepare test cases for runner
        test_cases = [
            {'input_data': tc.input_data, 'output_data': tc.output_data, 'is_hidden': tc.is_hidden}
            for tc in q.test_cases
        ]

        # Use the shared runner
        runner_result = run_test_cases(code, language, test_cases)
        results = []

        # Map runner results back to format expected by frontend
        for i, r in enumerate(runner_result['results']):
            # Get original input (runner doesn't return it)
            original_input = test_cases[i]['input_data']
            
            results.append({
                'input':    original_input,
                'expected': r['expected'],
                'actual':   r['actual'],
                'passed':   r['passed'],
                'error':    r.get('stderr', ''),
                'is_hidden': r.get('is_hidden', False), # Pass hidden status if frontend needs it
            })

        return results, runner_result['all_passed']

    @database_sync_to_async
    def mark_match_winner(self, user_id):
        """Set the match winner if not already set. Returns (winner_id, winner_username)."""
        try:
            t = Tournament.objects.get(id=self.tournament_id)
        except Exception:
            return None, ''

        for m in t.matches:
            if m.match_id == self.match_id:
                if m.winner_id:
                    return None, ''   # already decided
                # Verify this player is actually in the match
                if user_id not in (m.player1_id, m.player2_id):
                    return None, ''
                m.winner_id = user_id
                m.winner_username = dict(t.participant_usernames).get(user_id, '')
                m.status = 'done'
                t.save()
                return m.winner_id, m.winner_username

        return None, ''

    @database_sync_to_async
    def force_match_winner(self, winner_id):
        """Teacher-forced winner. Returns (winner_id, winner_username)."""
        try:
            t = Tournament.objects.get(id=self.tournament_id)
        except Exception:
            return None, ''

        for m in t.matches:
            if m.match_id == self.match_id:
                if winner_id not in (m.player1_id, m.player2_id):
                    return None, ''
                m.winner_id = winner_id
                m.winner_username = dict(t.participant_usernames).get(winner_id, '')
                m.status = 'done'
                t.save()
                return m.winner_id, m.winner_username

        return None, ''
