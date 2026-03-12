from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/battle/(?P<room_name>\w+)/$', consumers.BattleConsumer.as_asgi()),
    re_path(
        r'ws/tournament/(?P<tournament_id>[^/]+)/match/(?P<match_id>[^/]+)/$',
        consumers.TournamentConsumer.as_asgi(),
    ),
]
