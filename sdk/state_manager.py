import asyncio
from alphagateway.shared.database_module import db
from alphagateway.shared.redis_module import redis_bus

class AlphaStateManager:
    def __init__(self, alpha_id: str):
        self.alpha_id = alpha_id
        self.lock_prefix = f"lock:alpha:{alpha_id}:"

    async def get_current_state(self, symbol: str):
        """Query DB để lấy vị thế thực tế và lệnh đang treo"""
        # Dùng async gom cả 2 query để giảm latency
        pos_task = db.pool.fetchrow(
            "SELECT * FROM alpha_positions WHERE alpha_id = $1 AND symbol = $2", 
            self.alpha_id, symbol
        )
        orders_task = db.pool.fetch(
            "SELECT * FROM alpha_orders WHERE alpha_id = $1 AND symbol = $2 AND status = 'NEW'",
            self.alpha_id, symbol
        )
        pos, orders = await asyncio.gather(pos_task, orders_task)
        return {"position": dict(pos) if pos else None, "pending_orders": [dict(o) for o in orders]}

    async def acquire_order_lock(self, symbol: str, ttl: float = 2.0):
        """Chặn Alpha gửi lệnh trùng lặp khi lệnh trước chưa xử lý xong"""
        key = f"{self.lock_prefix}{symbol}"
        return await redis_bus.client.set(key, "LOCKED", nx=True, pexpire=int(ttl * 1000))

    async def release_order_lock(self, symbol: str):
        await redis_bus.client.delete(f"{self.lock_prefix}{symbol}")