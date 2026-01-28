# shared/redis_module.py
import redis.asyncio as redis
from shared.config import settings

class RedisBus:
    def __init__(self):
        self.client: redis.Redis = None

    async def connect(self):
        # Pool size được cấu hình lớn để chịu tải 500 Alphas
        self.client = redis.from_url(
            settings.REDIS_URL, 
            decode_responses=False, # Giữ raw bytes để tối ưu
            max_connections=100
        )

    async def disconnect(self):
        if self.client:
            await self.client.close()

redis_bus = RedisBus()