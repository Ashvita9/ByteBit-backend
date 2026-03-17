from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs

User = get_user_model()

@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class JwtAuthMiddleware(BaseMiddleware):
    """
    Middleware to authenticate user via 'token' query parameter using SimpleJWT.
    Usage: ws://.../?token=<access_token>
    """
    async def __call__(self, scope, receive, send):
        # 1. Try to get token from query string
        try:
            query_string = scope.get('query_string', b'').decode()
            params = parse_qs(query_string)
            token_list = params.get('token')
            token = token_list[0] if token_list else None
            
            if token:
                # 2. Validate token
                access_token = AccessToken(token)
                # 3. Get user
                user = await get_user(access_token['user_id'])
                if user and user.is_active:
                    scope['user'] = user
                # If invalid, we assume the previous middleware (AuthMiddlewareStack) 
                # might have set a user (via session), or we leave it as Anonymous.
                # But typically if a token is provided and fails, we might want to enforce failure?
                # For now, if token is valid, we OVERWRITE. If not, we do nothing (keep existing scope['user']).
                
        except Exception as e:
            # Token invalid or expired
            pass
            
        return await super().__call__(scope, receive, send)
