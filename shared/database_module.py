import asyncpg
import logging
from alphagateway.shared.config import settings

logger = logging.getLogger("DB_MODULE")

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=settings.POSTGRES_DSN,
                    min_size=10,
                    max_size=50,
                    # Tự động hủy các query chạy quá 30s để tránh nghẽn
                    command_timeout=30,
                    # Đảm bảo pool luôn khỏe
                    max_queries =1000,
                    max_inactive_connection_lifetime=300 
                )
                logger.info("✅ Database connection pool established")
            except Exception as e:
                logger.error(f"❌ Failed to connect to DB: {e}")
                raise

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")

db = Database()