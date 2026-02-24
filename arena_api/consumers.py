import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import CoderProfile, CodingTask, Submission


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
