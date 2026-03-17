from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs

@database_sync_to_async
def get_user(user_id):
    try:
        User = get_user_model()
        return User.objects.get(id=user_id)
    except Exception:
        return AnonymousUser()

class JwtAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        try:
            from rest_framework_simplejwt.tokens import AccessToken

            query_string = scope.get('query_string', b'').decode()
            params = parse_qs(query_string)
            token_list = params.get('token')
            token = token_list[0] if token_list else None
            
            if token:
                access_token = AccessToken(token)
                user = await get_user(access_token['user_id'])
                if user and user.is_active:
                    scope['user'] = user
                
        except Exception:
            pass
            
        return await super().__call__(scope, receive, send)
