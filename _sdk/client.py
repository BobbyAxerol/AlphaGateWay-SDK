"""
AlphaGateway SDK v4 — Pure HTTP Client
=======================================
SDK giao tiếp với Gateway qua HTTP API.
Không có DB connection, không có Redis connection.
Mọi state đọc qua StateProvider (DB read-only) hoặc /health endpoint.

Cách dùng nhanh:
    sdk = AlphaGateWaySDK(
        base_url="http://gateway_service:8000",
        alpha_id="alpha_001",
        api_key="your-secret-key"
    )
    await sdk.connect()
    res, ok = await sdk.open_long("BTCUSDT", qty=0.01)
    await sdk.close()
"""

import time
import httpx
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from sdk.models import Side, PositionSide, OrderType, OrderIntent

logger = logging.getLogger("AlphaSDK_V4")


class AlphaGateWaySDK:
    """
    Pure HTTP SDK — gọi Gateway API, không tự kết nối DB hay Redis.

    Args:
        base_url:  URL của Gateway service, vd: "http://gateway_service:8000"
        alpha_id:  ID định danh Alpha, phải tồn tại trong bảng alphas
        api_key:   Secret key, đăng ký bằng lệnh Redis:
                   HSET gate:apikeys <alpha_id> <api_key>
        timeout:   Timeout mỗi request (giây), default 2.0
    """

    def __init__(self, base_url: str, alpha_id: str, api_key: str, timeout: float = 2.0):
        self.base_url = base_url.rstrip('/')
        self.alpha_id = alpha_id
        self.api_key  = api_key
        self.timeout  = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def connect(self):
        """Khởi tạo HTTP connection pool. Gọi 1 lần khi strategy startup."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "X-API-Key":     self.api_key,
                "Content-Type":  "application/json",
            },
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
        )
        logger.info(f"✅ AlphaSDK v4 connected → {self.base_url} (alpha={self.alpha_id})")

    async def close(self):
        """Đóng connection pool. Gọi khi strategy shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ------------------------------------------------------------------ #
    # NHÓM 1 — Lệnh đơn MARKET / LIMIT                                   #
    # ------------------------------------------------------------------ #

    async def open_long(self, symbol: str, qty: float,
                        price: Optional[float] = None,
                        time_in_force: str = "GTC") -> Tuple[Dict, bool]:
        """Mở vị thế LONG. price=None → MARKET, price=x → LIMIT."""
        return await self._submit(
            symbol=symbol, side=Side.BUY, qty=qty, price=price,
            pos_side=PositionSide.LONG, reduce_only=False,
            intent=OrderIntent.OPEN, time_in_force=time_in_force,
        )

    async def open_short(self, symbol: str, qty: float,
                         price: Optional[float] = None,
                         time_in_force: str = "GTC") -> Tuple[Dict, bool]:
        """Mở vị thế SHORT. price=None → MARKET, price=x → LIMIT."""
        return await self._submit(
            symbol=symbol, side=Side.SELL, qty=qty, price=price,
            pos_side=PositionSide.SHORT, reduce_only=False,
            intent=OrderIntent.OPEN, time_in_force=time_in_force,
        )

    async def close_long(self, symbol: str, qty: float,
                         price: Optional[float] = None) -> Tuple[Dict, bool]:
        """Đóng/reduce vị thế LONG (SELL reduce_only)."""
        return await self._submit(
            symbol=symbol, side=Side.SELL, qty=qty, price=price,
            pos_side=PositionSide.LONG, reduce_only=True,
            intent=OrderIntent.CLOSE,
        )

    async def close_short(self, symbol: str, qty: float,
                          price: Optional[float] = None) -> Tuple[Dict, bool]:
        """Đóng/reduce vị thế SHORT (BUY reduce_only)."""
        return await self._submit(
            symbol=symbol, side=Side.BUY, qty=qty, price=price,
            pos_side=PositionSide.SHORT, reduce_only=True,
            intent=OrderIntent.CLOSE,
        )

    # ------------------------------------------------------------------ #
    # NHÓM 2 — Stop Loss / Take Profit / Conditional                      #
    # ------------------------------------------------------------------ #

    async def set_stop_loss(self, symbol: str, pos_side: PositionSide,
                            stop_price: float, qty: float = 0,
                            close_position: bool = True) -> Tuple[Dict, bool]:
        """
        Đặt Stop Loss Market.

        Args:
            stop_price:     Giá kích hoạt SL
            close_position: True → đóng toàn bộ vị thế khi kích hoạt
        """
        side = Side.SELL if pos_side == PositionSide.LONG else Side.BUY
        payload = self._build_payload(
            symbol=symbol, side=side, qty=0 if close_position else qty,
            price=None, stop_price=stop_price, pos_side=pos_side,
            o_type=OrderType.STOP_MARKET, reduce_only=True,
            intent=OrderIntent.CLOSE, close_position=close_position,
        )
        return await self._request("/submit", payload)

    async def set_take_profit(self, symbol: str, pos_side: PositionSide,
                              stop_price: float, qty: float = 0,
                              close_position: bool = True) -> Tuple[Dict, bool]:
        """
        Đặt Take Profit Market.

        Args:
            stop_price:     Giá kích hoạt TP
            close_position: True → đóng toàn bộ vị thế khi kích hoạt
        """
        side = Side.SELL if pos_side == PositionSide.LONG else Side.BUY
        payload = self._build_payload(
            symbol=symbol, side=side, qty=0 if close_position else qty,
            price=None, stop_price=stop_price, pos_side=pos_side,
            o_type=OrderType.TAKE_PROFIT_MARKET, reduce_only=True,
            intent=OrderIntent.CLOSE, close_position=close_position,
        )
        return await self._request("/submit", payload)

    async def set_stop_limit(self, symbol: str, pos_side: PositionSide,
                             stop_price: float, limit_price: float, qty: float,
                             time_in_force: str = "GTC") -> Tuple[Dict, bool]:
        """Stop Limit — khớp tại limit_price sau khi kích hoạt ở stop_price."""
        side = Side.SELL if pos_side == PositionSide.LONG else Side.BUY
        payload = self._build_payload(
            symbol=symbol, side=side, qty=qty,
            price=limit_price, stop_price=stop_price,
            pos_side=pos_side, o_type=OrderType.STOP,
            reduce_only=True, intent=OrderIntent.CLOSE,
            time_in_force=time_in_force,
        )
        return await self._request("/submit", payload)

    async def set_trailing_stop(self, symbol: str, pos_side: PositionSide,
                                callback_rate: float, qty: float = 0,
                                activation_price: Optional[float] = None,
                                close_position: bool = True) -> Tuple[Dict, bool]:
        """
        Trailing Stop Market — trailing theo callback_rate %.

        Args:
            callback_rate:    Phần trăm trailing (1.0 = 1%). Range: 0.1–5.0
            activation_price: Giá kích hoạt trailing (optional, mặc định ngay lập tức)
        """
        side = Side.SELL if pos_side == PositionSide.LONG else Side.BUY
        payload = self._build_payload(
            symbol=symbol, side=side, qty=0 if close_position else qty,
            price=None, stop_price=activation_price,
            pos_side=pos_side, o_type=OrderType.TRAILING_STOP_MARKET,
            reduce_only=True, intent=OrderIntent.CLOSE,
            close_position=close_position,
        )
        payload["callback_rate"] = callback_rate
        return await self._request("/submit", payload)

    # ------------------------------------------------------------------ #
    # NHÓM 3 — Quản lý lệnh đang treo                                     #
    # ------------------------------------------------------------------ #

    async def update_order(self, symbol: str, orig_client_order_id: str,
                           new_qty: float, new_price: float) -> Tuple[Dict, bool]:
        """
        Sửa lệnh LIMIT đang chờ (cancel + replace).
        Risk Engine sẽ giải phóng virtual exposure của lệnh cũ trước khi đặt mới.
        """
        payload = {
            "alpha_id":             self.alpha_id,
            "symbol":               symbol,
            "orig_client_order_id": orig_client_order_id,
            "new_client_order_id":  self._gen_id(symbol),
            "quantity":             new_qty,
            "price":                new_price,
            "intent":               OrderIntent.UPDATE.value,
            "alpha_send_ts":        time.time(),
        }
        return await self._request("/update", payload)

    async def cancel_order(self, symbol: str,
                           orig_client_order_id: str) -> Tuple[Dict, bool]:
        """Hủy lệnh LIMIT đang treo."""
        payload = {
            "alpha_id":             self.alpha_id,
            "symbol":               symbol,
            "orig_client_order_id": orig_client_order_id,
            "new_client_order_id":  self._gen_id(symbol),
            "quantity":             0,
            "price":                0,
            "intent":               "CANCEL",
            "alpha_send_ts":        time.time(),
        }
        return await self._request("/update", payload)

    # ------------------------------------------------------------------ #
    # NHÓM 4 — Bulk / Basket                                              #
    # ------------------------------------------------------------------ #

    async def bulk_open_long(self, orders: List[Dict]) -> List[Dict]:
        """
        Mở nhiều LONG cùng lúc.

        orders: [{"symbol": str, "qty": float, "price": float|None}, ...]
        """
        payloads = [
            self._build_payload(
                symbol=o['symbol'], side=Side.BUY, qty=o['qty'],
                price=o.get('price'), pos_side=PositionSide.LONG,
                o_type=OrderType.LIMIT if o.get('price') else OrderType.MARKET,
                reduce_only=False, intent=OrderIntent.OPEN,
            )
            for o in orders
        ]
        return await self._bulk_chunks(payloads)

    async def bulk_open_short(self, orders: List[Dict]) -> List[Dict]:
        """Mở nhiều SHORT cùng lúc. Format giống bulk_open_long."""
        payloads = [
            self._build_payload(
                symbol=o['symbol'], side=Side.SELL, qty=o['qty'],
                price=o.get('price'), pos_side=PositionSide.SHORT,
                o_type=OrderType.LIMIT if o.get('price') else OrderType.MARKET,
                reduce_only=False, intent=OrderIntent.OPEN,
            )
            for o in orders
        ]
        return await self._bulk_chunks(payloads)

    async def bulk_close(self, closes: List[Dict]) -> List[Dict]:
        """
        Đóng nhiều vị thế cùng lúc.

        closes: [{"symbol": str, "qty": float, "pos_side": "LONG"|"SHORT", "price": float|None}, ...]
        """
        payloads = []
        for c in closes:
            ps   = PositionSide(c.get('pos_side', 'LONG'))
            side = Side.SELL if ps == PositionSide.LONG else Side.BUY
            payloads.append(self._build_payload(
                symbol=c['symbol'], side=side, qty=c['qty'],
                price=c.get('price'), pos_side=ps,
                o_type=OrderType.LIMIT if c.get('price') else OrderType.MARKET,
                reduce_only=True, intent=OrderIntent.CLOSE,
            ))
        return await self._bulk_chunks(payloads)

    # ------------------------------------------------------------------ #
    # NHÓM 5 — Rebalance & Emergency                                      #
    # ------------------------------------------------------------------ #

    async def rebalance_portfolio(self, target_states: List[Dict]) -> List[Dict]:
        """
        Điều chỉnh portfolio về trạng thái mục tiêu (MARKET orders).

        target_states: [
            {
                "symbol":      str,
                "target_qty":  float,    # > 0 = LONG, < 0 = SHORT, 0 = đóng hết
                "current_qty": float,    # caller tự query, không để SDK query DB
                "pos_side":    str,      # "LONG" | "SHORT" | "BOTH"  (optional)
            },
            ...
        ]
        """
        all_orders = []
        for item in target_states:
            symbol     = item['symbol']
            target_qty = float(item['target_qty'])
            curr_qty   = float(item.get('current_qty', 0.0))
            p_side     = PositionSide(item.get('pos_side', 'BOTH'))

            delta = target_qty - curr_qty
            if abs(delta) < 1e-9:
                continue

            is_reduce = abs(target_qty) < abs(curr_qty) or target_qty == 0
            if p_side in (PositionSide.LONG, PositionSide.BOTH):
                side = Side.BUY if delta > 0 else Side.SELL
            else:
                side = Side.SELL if delta > 0 else Side.BUY

            all_orders.append(self._build_payload(
                symbol=symbol, side=side, qty=abs(delta),
                price=None, pos_side=p_side,
                o_type=OrderType.MARKET,
                reduce_only=is_reduce,
                intent=OrderIntent.REDUCE if is_reduce else OrderIntent.OPEN,
            ))

        if not all_orders:
            return [{"status": "NO_OP", "count": 0}]
        return await self._bulk_chunks(all_orders)

    async def emergency_close_all(self, positions: List[Dict]) -> List[Dict]:
        """
        Đóng khẩn tất cả vị thế bằng MARKET order.

        Args:
            positions: list từ StateProvider.get_active_positions()
                       cần có field 'symbol' và 'quantity'
        """
        if not positions:
            return [{"status": "CLEAN", "count": 0}]

        targets = [
            {
                "symbol":      p['symbol'],
                "target_qty":  0,
                "current_qty": abs(float(p.get('quantity', 0))),
                "pos_side":    "LONG" if float(p.get('quantity', 0)) > 0 else "SHORT",
            }
            for p in positions
            if abs(float(p.get('quantity', 0))) > 1e-9
        ]
        return await self.rebalance_portfolio(targets)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _gen_id(self, symbol: str) -> str:
        """Generate unique client_order_id ≤ 36 ký tự (giới hạn Binance)."""
        sym_clean = symbol.replace("USDT", "").replace("/", "")[:6]
        return f"{self.alpha_id[:8]}_{sym_clean}_{int(time.time() * 1000)}"

    def _build_payload(
        self,
        symbol: str, side: Side, qty: float,
        price: Optional[float], pos_side: PositionSide,
        o_type: OrderType, reduce_only: bool, intent: OrderIntent,
        stop_price: Optional[float] = None,
        time_in_force: str = "GTC",
        close_position: bool = False,
    ) -> Dict:
        payload: Dict[str, Any] = {
            "alpha_id":        self.alpha_id,
            "client_order_id": self._gen_id(symbol),
            "symbol":          symbol.upper().replace("/", "").replace("-", ""),
            "side":            side.value,
            "position_side":   pos_side.value,
            "type":            o_type.value,
            "quantity":        qty,
            "reduce_only":     reduce_only,
            "intent":          intent.value,
            "alpha_send_ts":   time.time(),
            "exchange":        "BINANCE",
        }
        if price is not None:
            payload["price"] = price
        if stop_price is not None:
            payload["stop_price"] = stop_price
        if o_type == OrderType.LIMIT:
            payload["time_in_force"] = time_in_force
        if close_position:
            payload["close_position"] = True
        return payload

    async def _submit(
        self,
        symbol: str, side: Side, qty: float,
        price: Optional[float], pos_side: PositionSide,
        reduce_only: bool, intent: OrderIntent,
        time_in_force: str = "GTC",
        stop_price: Optional[float] = None,
    ) -> Tuple[Dict, bool]:
        o_type  = OrderType.LIMIT if price else OrderType.MARKET
        payload = self._build_payload(
            symbol=symbol, side=side, qty=qty, price=price,
            stop_price=stop_price, pos_side=pos_side, o_type=o_type,
            reduce_only=reduce_only, intent=intent,
            time_in_force=time_in_force,
        )
        return await self._request("/submit", payload)

    async def _request(self, endpoint: str, payload: Dict) -> Tuple[Dict, bool]:
        if not self._client:
            raise RuntimeError("SDK chưa connect. Gọi await sdk.connect() trước.")
        try:
            resp = await self._client.post(endpoint, json=payload)
            if resp.status_code == 202:
                return resp.json(), True
            logger.warning(f"⚠️ Gateway {resp.status_code} [{endpoint}]: {resp.text[:200]}")
            return resp.json() if resp.text else {"error": "empty_response"}, False
        except httpx.TimeoutException:
            logger.error(f"⏱ Timeout: {endpoint} | symbol={payload.get('symbol')}")
            return {"error": "TIMEOUT"}, False
        except Exception as e:
            logger.error(f"Network Error [{endpoint}]: {e}")
            return {"error": str(e)}, False

    async def _bulk_chunks(self, payloads: List[Dict], chunk_size: int = 5) -> List[Dict]:
        """
        Gửi lệnh theo chunk.
        chunk_size=5: Binance Futures giới hạn 5 lệnh/batch để tránh vượt weight.
        """
        results = []
        for i in range(0, len(payloads), chunk_size):
            chunk = payloads[i:i + chunk_size]
            res, _ = await self._request("/bulk", {
                "alpha_id":      self.alpha_id,
                "orders":        chunk,
                "alpha_send_ts": time.time(),
            })
            results.append(res if res else {"status": "FAILED"})
            if i + chunk_size < len(payloads):
                await asyncio.sleep(0.05)
        return results