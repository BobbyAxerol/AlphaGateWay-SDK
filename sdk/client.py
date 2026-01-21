import time
import httpx
import asyncio
import logging
from typing import List, Dict, Any, Optional
from alphagateway.sdk.models import Side, PositionSide, OrderType
from alphagateway.sdk.state_manager import AlphaStateManager

logger = logging.getLogger("AlphaSDK_V3")

class AlphaGateWaySDK:
    def __init__(self, base_url: str, alpha_id: str):
        self.base_url = base_url.rstrip('/')
        self.alpha_id = alpha_id
        self.state = AlphaStateManager(alpha_id)
        # Sử dụng AsyncClient cho hiệu năng cao
        self.http_client = httpx.AsyncClient(timeout=1.0, limits=httpx.Limits(max_keepalive_connections=20))

    def _gen_id(self, symbol: str) -> str:
        """Quy tắc ID: ALPHA_SYMBOL_MS"""
        return f"{self.alpha_id}_{symbol.replace('USDT','')}_{int(time.time()*1000)}"

    # --- CORE SENDER WITH RETRY & FALLBACK ---
    async def _request(self, method: str, endpoint: str, payload: Dict, retries: int = 2):
        url = f"{self.base_url}{endpoint}"
        for i in range(retries + 1):
            try:
                resp = await self.http_client.post(url, json=payload)
                if resp.status_code == 202: return resp.json(), True
                if resp.status_code == 429: # Rate limit
                    await asyncio.sleep(0.1 * (i + 1))
                    continue
                return resp.json(), False
            except Exception as e:
                if i == retries:
                    logger.error(f"🔥 SDK Fatal Error: {e}")
                    return {"status": "SDK_TIMEOUT"}, False
                await asyncio.sleep(0.05)

    # --- SMART ACTIONS ---
    async def smart_order(self, symbol: str, side: Side, qty: float, 
                          price: Optional[float] = None, 
                          pos_side: PositionSide = PositionSide.BOTH):
        """
        Gửi lệnh có cơ chế Locking bảo vệ. 
        Nếu đang có lệnh PENDING cho symbol này, SDK sẽ block ngay lập tức.
        """
        # 1. Check & Acquire Lock
        if not await self.state.acquire_order_lock(symbol):
            logger.warning(f"⚠️ Order Blocked: {symbol} is already in transition.")
            return None

        payload = {
            "alpha_id": self.alpha_id,
            "client_order_id": self._gen_id(symbol),
            "symbol": symbol,
            "side": side.value,
            "position_side": pos_side.value,
            "type": "LIMIT" if price else "MARKET",
            "quantity": qty,
            "price": price,
            "alpha_send_ts": time.time()
        }
        
        res, success = await self._request("POST", "/submit", payload)
        
        # Nếu gửi thất bại, giải phóng lock ngay để Alpha thử lại
        if not success:
            await self.state.release_order_lock(symbol)
            
        return res

    async def sync_adjust_position(self, symbol: str, target_qty: float, price: Optional[float] = None):
        """
        Hàm cực mạnh cho Alpha: Tự động nhìn DB -> Tính Delta -> Đẩy lệnh.
        Alpha chỉ cần gọi: sdk.sync_adjust_position("BTCUSDT", 0.5)
        """
        data = await self.state.get_current_state(symbol)
        pos = data['position']
        
        # 1. Tính toán delta
        current_qty = float(pos['volume']) if pos else 0.0
        # Ở Binance Hedge Mode, volume luôn dương, ta phải check side
        if pos and pos['position_type'] == 'SHORT':
            current_qty = -current_qty
            
        delta = target_qty - current_qty
        if abs(delta) < 1e-8: return "NO_CHANGE"

        # 2. Xác định Side & PositionSide
        side = Side.BUY if delta > 0 else Side.SELL
        # Giả định dùng BOTH cho One-way hoặc phải truyền LONG/SHORT tùy setup
        return await self.smart_order(symbol, side, abs(delta), price)

    async def bulk_rebalance(self, target_portfolio: Dict[str, float]):
        """
        Rebalance toàn bộ danh mục bằng 1 lệnh Bulk duy nhất.
        target_portfolio = {"BTCUSDT": 0.5, "ETHUSDT": 10.0}
        """
        bulk_orders = []
        for symbol, t_qty in target_portfolio.items():
            data = await self.state.get_current_state(symbol)
            curr_qty = float(data['position']['volume']) if data['position'] else 0.0
            if data['position'] and data['position']['position_type'] == 'SHORT': curr_qty = -curr_qty
            
            delta = t_qty - curr_qty
            if abs(delta) > 0:
                bulk_orders.append({
                    "symbol": symbol,
                    "side": "BUY" if delta > 0 else "SELL",
                    "type": "MARKET",
                    "quantity": abs(delta),
                    "position_side": "BOTH"
                })
        
        if bulk_orders:
            return await self._request("POST", "/bulk", {
                "alpha_id": self.alpha_id,
                "orders": bulk_orders,
                "alpha_send_ts": time.time()
            })

    async def cancel_all_for_symbol(self, symbol: str):
        """Dọn sạch lệnh treo trước khi tính toán logic mới"""
        data = await self.state.get_current_state(symbol)
        for order in data['pending_orders']:
            # Gửi lệnh cancel cho từng ID
            pass