import time
import httpx
import asyncio
import logging
from typing import List, Dict, Any, Optional
from sdk.models import Side, PositionSide, OrderType, OrderIntent
from sdk.state_manager import AlphaStateManager
from sdk.exceptions import GatewayTimeout, GatewayReject, LockActiveException

logger = logging.getLogger("AlphaSDK_V3")

class AlphaGateWaySDK:
    def __init__(self, base_url: str, alpha_id: str):
        self.base_url = base_url.rstrip('/')
        self.alpha_id = alpha_id
        self.state = AlphaStateManager(alpha_id)
        self.client = httpx.AsyncClient(
            timeout=2.0, 
            limits=httpx.Limits(max_keepalive_connections=100, max_connections=100)
        )

    def _gen_id(self, symbol: str) -> str:
        sym_clean = symbol.replace("USDT", "").replace("/", "")
        return f"{self.alpha_id}_{sym_clean}_{int(time.time() * 1000)}"

    async def _request(self, endpoint: str, payload: Dict):
        url = f"{self.base_url}{endpoint}"
        try:
            resp = await self.client.post(url, json=payload)
            if resp.status_code == 202:
                return resp.json(), True
            return resp.json(), False
        except Exception as e:
            logger.error(f"🔥 Network Error: {url} | {e}")
            return None, False

    # --- NHÓM 1: LỆNH CHIẾN THUẬT ĐƠN LẺ ---

    async def open_long(self, symbol: str, qty: float, price: Optional[float] = None):
        return await self._smart_submit(symbol, Side.BUY, qty, price, PositionSide.LONG, intent=OrderIntent.OPEN)

    async def open_short(self, symbol: str, qty: float, price: Optional[float] = None):
        return await self._smart_submit(symbol, Side.SELL, qty, price, PositionSide.SHORT, intent=OrderIntent.OPEN)

    async def close_long(self, symbol: str, qty: float, price: Optional[float] = None):
        return await self._smart_submit(symbol, Side.SELL, qty, price, PositionSide.LONG, reduce_only=True, intent=OrderIntent.CLOSE)

    async def close_short(self, symbol: str, qty: float, price: Optional[float] = None):
        return await self._smart_submit(symbol, Side.BUY, qty, price, PositionSide.SHORT, reduce_only=True, intent=OrderIntent.CLOSE)

    # --- NHÓM 2: LỆNH BULK THEO HƯỚNG (BASKET TRADING) ---

    async def bulk_open_long(self, orders: List[Dict]):
        """orders = [{'symbol': 'BTCUSDT', 'qty': 0.1}, {'symbol': 'ETHUSDT', 'qty': 1.0}]"""
        payloads = []
        for o in orders:
            payloads.append(self._build_payload(
                o['symbol'], Side.BUY, o['qty'], o.get('price'), 
                PositionSide.LONG, "LIMIT" if o.get('price') else "MARKET", False, OrderIntent.OPEN
            ))
        return await self._submit_bulk_chunks(payloads)

    async def bulk_open_short(self, orders: List[Dict]):
        payloads = []
        for o in orders:
            payloads.append(self._build_payload(
                o['symbol'], Side.SELL, o['qty'], o.get('price'), 
                PositionSide.SHORT, "LIMIT" if o.get('price') else "MARKET", False, OrderIntent.OPEN
            ))
        return await self._submit_bulk_chunks(payloads)

    # --- NHÓM 3: REBALANCE VÀ TỰ ĐỘNG HÓA ---

    async def rebalance_portfolio(self, target_states: List[Dict]):
        """Tối ưu Rebalance: Tự tính Delta, gán Intent, chia Batch 10."""
        all_orders = []
        for item in target_states:
            symbol = item['symbol']
            target_qty = float(item['target_qty'])
            p_side = PositionSide(item.get('pos_side', 'BOTH'))

            state = await self.state.get_current_state(symbol)
            pos = state['position']
            curr_qty = float(pos['volume']) if pos else 0.0
            
            delta = target_qty - curr_qty
            if abs(delta) < 1e-8: continue

            is_reduce = target_qty < curr_qty
            if p_side in [PositionSide.LONG, PositionSide.BOTH]:
                side = Side.BUY if delta > 0 else Side.SELL
            else:
                side = Side.SELL if delta > 0 else Side.BUY

            all_orders.append(self._build_payload(
                symbol, side, abs(delta), None, p_side, "MARKET", 
                is_reduce, OrderIntent.REDUCE if is_reduce else OrderIntent.OPEN
            ))
        return await self._submit_bulk_chunks(all_orders)

    async def emergency_close_all(self):
        """Đóng toàn bộ vị thế đang active"""
        active_positions = await self.state.get_active_positions()
        if not active_positions: 
            return {"status": "CLEAN", "count": 0}
        
        targets = [{"symbol": p['symbol'], "target_qty": 0, "pos_side": p['position_side']} for p in active_positions]
        return await self.rebalance_portfolio(targets)

    # --- NHÓM 4: QUẢN TRỊ LỆNH TREO & RỦI RO ---

    async def update_order(self, symbol: str, orig_id: str, new_qty: float, new_price: float):
        payload = {
            "alpha_id": self.alpha_id,
            "symbol": symbol,
            "orig_client_order_id": orig_id,
            "new_client_order_id": self._gen_id(symbol),
            "quantity": new_qty,
            "price": new_price,
            "intent": OrderIntent.UPDATE,
            "alpha_send_ts": time.time()
        }
        return await self._request("/update", payload)

    async def set_sl_tp(self, symbol: str, pos_side: PositionSide, sl_price: float = None, tp_price: float = None):
        orders = []
        side = Side.SELL if pos_side == PositionSide.LONG else Side.BUY
        if sl_price:
            orders.append(self._build_payload(symbol, side, 0, sl_price, pos_side, "STOP_MARKET", True, OrderIntent.CLOSE))
        if tp_price:
            orders.append(self._build_payload(symbol, side, 0, tp_price, pos_side, "TAKE_PROFIT_MARKET", True, OrderIntent.CLOSE))
        return await self._submit_bulk_chunks(orders)

    # --- LÕI XỬ LÝ HỆ THỐNG ---

    async def _smart_submit(self, symbol, side, qty, price, pos_side, reduce_only=False, intent=OrderIntent.OPEN):
        if not await self.state.acquire_order_lock(symbol):
            logger.warning(f"⚠️ Locked: {symbol}")
            return {"status": "SDK_LOCKED"}, False

        payload = self._build_payload(symbol, side, qty, price, pos_side, "LIMIT" if price else "MARKET", reduce_only, intent)
        res, ok = await self._request("/submit", payload)
        if not ok: 
            await self.state.release_order_lock(symbol)
        return res, ok

    async def _submit_bulk_chunks(self, payloads: List[Dict]):
        """Chia nhỏ 10 lệnh/batch để tránh lỗi sàn và gateway"""
        results = []
        for i in range(0, len(payloads), 10):
            chunk = payloads[i:i + 10]
            res, ok = await self._request("/bulk", {
                "alpha_id": self.alpha_id,
                "orders": chunk,
                "alpha_send_ts": time.time()
            })
            results.append(res)
            await asyncio.sleep(0.05)
        return results

    def _build_payload(self, symbol, side, qty, price, pos_side, o_type, reduce_only, intent):
        return {
            "alpha_id": self.alpha_id,
            "client_order_id": self._gen_id(symbol),
            "symbol": symbol,
            "side": side.value,
            "position_side": pos_side.value,
            "type": o_type,
            "quantity": qty,
            "price": price,
            "reduce_only": reduce_only,
            "intent": intent.value if isinstance(intent, OrderIntent) else intent,
            "alpha_send_ts": time.time(),
            "exchange": "BINANCE"
        }