from enum import Enum
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Union
import time

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
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"

class OrderIntent(str, Enum):
    OPEN = "OPEN"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"
    UPDATE = "UPDATE"

class AlphaOrder(BaseModel):
    alpha_id: str
    client_order_id: str
    symbol: str
    side: Side
    position_side: PositionSide = PositionSide.BOTH
    order_type: OrderType = Field(alias="type") 
    quantity: float = Field(gt=0)
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    post_only: bool = False
    exchange: str = "BINANCE"
    intent: OrderIntent = OrderIntent.OPEN
    alpha_send_ts: float = Field(default_factory=time.time)

    @field_validator('symbol')
    @classmethod
    def format_symbol(cls, v):
        return v.upper().replace("/", "").replace("-", "")

    class Config:
        populate_by_name = True

class BulkOrderRequest(BaseModel):
    alpha_id: str
    orders: List[AlphaOrder]
    alpha_send_ts: float = Field(default_factory=time.time)

class UpdateOrderIntent(BaseModel):
    alpha_id: str
    symbol: str
    orig_client_order_id: str
    new_client_order_id: str
    quantity: float
    price: float
    intent: OrderIntent = OrderIntent.UPDATE
    alpha_send_ts: float = Field(default_factory=time.time)