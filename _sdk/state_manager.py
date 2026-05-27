import asyncio
import logging
from shared.database_module import db
from shared.redis_module import redis_bus
from typing import List, Dict, Any, Optional

logger = logging.getLogger("StateManager")

class AlphaStateManager:
    def __init__(self, alpha_id: str):
        self.alpha_id = alpha_id
        self.lock_prefix = f"lock:alpha:{alpha_id}:"

    async def get_current_state(self, symbol: str):
        """Query DB để lấy vị thế thực tế và lệnh đang treo của 1 symbol"""
        if not db.pool:
            logger.error("❌ DB Pool not initialized")
            return {"position": None, "pending_orders": []}

        pos_task = db.pool.fetchrow(
            "SELECT * FROM alpha_positions WHERE alpha_id = $1 AND symbol = $2", 
            self.alpha_id, symbol
        )
        # Dùng binance_sent_orders thay vì alpha_orders (không tồn tại)
        # Lấy các lệnh đang chờ khớp của symbol này
        orders_task = db.pool.fetch(
            """SELECT client_order_id, symbol, side, type, price, orig_qty, status, intent
               FROM binance_sent_orders
               WHERE alpha_id = $1 AND symbol = $2
                 AND status IN ('PENDING', 'NEW', 'PARTIALLY_FILLED')
               ORDER BY sent_at DESC LIMIT 20""",
            self.alpha_id, symbol
        )
        pos, orders = await asyncio.gather(pos_task, orders_task)
        return {"position": dict(pos) if pos else None, "pending_orders": [dict(o) for o in orders]}

    async def get_active_positions(self) -> List[Dict]:
        """Lấy tất cả vị thế đang có quantity != 0 của Alpha này để Rebalance/Emergency"""
        if not db.pool:
            return []
            
        rows = await db.pool.fetch(
            # quantity là tên cột đúng trong alpha_positions (không phải volume)
            "SELECT symbol, quantity, entry_price, pending_buy_qty, pending_sell_qty "
            "FROM alpha_positions WHERE alpha_id = $1 AND quantity != 0",
            self.alpha_id
        )
        return [dict(r) for r in rows]

    async def acquire_order_lock(self, symbol: str, ttl: float = 2.0):
        """Sử dụng Redis để lock symbol tránh bắn lệnh trùng lặp"""
        if not redis_bus.client:
            logger.error("❌ Redis client not connected. Check redis_bus.connect()")
            return False # Hoặc True tùy vào việc bạn muốn cho phép trade khi mất Redis không

        key = f"{self.lock_prefix}{symbol}"
        try:
            # redis-py dùng px= (milliseconds), không phải pexpire=
            return await redis_bus.client.set(key, "LOCKED", nx=True, px=int(ttl * 1000))
        except Exception as e:
            logger.error(f"🔥 Redis Lock Error: {e}")
            return False

    async def release_order_lock(self, symbol: str):
        if not redis_bus.client:
            return
        try:
            await redis_bus.client.delete(f"{self.lock_prefix}{symbol}")
        except Exception as e:
            logger.error(f"🔥 Redis Release Error: {e}")