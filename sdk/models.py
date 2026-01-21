from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List

class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"

class AlphaOrder(BaseModel):
    alpha_id: str
    client_order_id: str
    symbol: str
    side: Side
    position_side: PositionSide = PositionSide.BOTH
    order_type: OrderType = Field(alias="type")
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    post_only: bool = False
    alpha_send_ts: float