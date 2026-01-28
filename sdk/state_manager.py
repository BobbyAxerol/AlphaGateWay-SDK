import asyncio
from shared.database_module import db
from shared.redis_module import redis_bus
from typing import List, Dict, Any, Optional

class AlphaStateManager:
    def __init__(self, alpha_id: str):
        self.alpha_id = alpha_id
        self.lock_prefix = f"lock:alpha:{alpha_id}:"

    async def get_current_state(self, symbol: str):
        """Query DB để lấy vị thế thực tế và lệnh đang treo của 1 symbol"""
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

    async def get_active_positions(self) -> List[Dict]:
        """Lấy tất cả vị thế đang có volume > 0 của Alpha này để Rebalance/Emergency"""
        rows = await db.pool.fetch(
            "SELECT symbol, volume, position_side FROM alpha_positions WHERE alpha_id = $1 AND volume > 0",
            self.alpha_id
        )
        return [dict(r) for r in rows]

    async def acquire_order_lock(self, symbol: str, ttl: float = 2.0):
        key = f"{self.lock_prefix}{symbol}"
        return await redis_bus.client.set(key, "LOCKED", nx=True, pexpire=int(ttl * 1000))

    async def release_order_lock(self, symbol: str):
        await redis_bus.client.delete(f"{self.lock_prefix}{symbol}")