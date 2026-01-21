import pandas as pd
from alphagateway.shared.database_module import db

class StateProvider:
    """Helper class giúp Alpha truy vấn trạng thái từ DB & Redis"""
    def __init__(self, alpha_id: str):
        self.alpha_id = alpha_id

    async def get_active_positions(self, symbol: str = None):
        """Lấy vị thế hiện tại của Alpha này từ DB"""
        query = "SELECT * FROM alpha_positions WHERE alpha_id = $1"
        args = [self.alpha_id]
        if symbol:
            query += " AND symbol = $2"
            args.append(symbol)
        
        rows = await db.pool.fetch(query, *args)
        return [dict(r) for r in rows]

    async def get_pending_orders(self, symbol: str = None):
        """Lấy danh sách lệnh đang treo trên sàn"""
        query = "SELECT * FROM alpha_orders WHERE alpha_id = $1 AND status IN ('NEW', 'PARTIALLY_FILLED')"
        args = [self.alpha_id]
        if symbol:
            query += " AND symbol = $2"
            args.append(symbol)
        
        rows = await db.pool.fetch(query, *args)
        return [dict(r) for r in rows]