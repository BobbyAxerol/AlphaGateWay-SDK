import pandas as pd
from shared.database_module import db  # Fix: bỏ prefix alphagateway. (chạy từ root alphagateway/)

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
        """Lấy danh sách lệnh đang treo trên sàn từ binance_sent_orders"""
        # Fix: bảng đúng là binance_sent_orders, không phải alpha_orders
        query = """
            SELECT client_order_id, symbol, side, type, price, orig_qty, executed_qty, status, intent, sent_at
            FROM binance_sent_orders 
            WHERE alpha_id = $1 AND status IN ('PENDING', 'NEW', 'PARTIALLY_FILLED')
        """
        args = [self.alpha_id]
        if symbol:
            query += " AND symbol = $2"
            args.append(symbol)
        query += " ORDER BY sent_at DESC"
        
        rows = await db.pool.fetch(query, *args)
        return [dict(r) for r in rows]

    async def get_ledger(self):
        """Lấy thông tin tài khoản / balance của Alpha"""
        row = await db.pool.fetchrow(
            "SELECT * FROM alpha_ledger WHERE alpha_id = $1", self.alpha_id
        )
        return dict(row) if row else None