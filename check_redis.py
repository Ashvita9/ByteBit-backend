import os
import redis
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1')
print(f"Testing connection to Redis at: {redis_url}")

try:
    r = redis.from_url(redis_url)
    r.ping()
    print("Redis connection successful!")
except redis.ConnectionError as e:
    print(f"Redis connection failed: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
