from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from enum import Enum

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"

class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"

@dataclass
class Position:
    """Represents an open position"""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    current_price: float
    leverage: float
    unrealized_pnl: float
    liquidation_price: Optional[float] = None
    margin: Optional[float] = None
    timestamp: Optional[datetime] = None
    
    @property
    def notional_value(self) -> float:
        """Calculate notional value of position"""
        return self.size * self.current_price
    
    @property
    def pnl_percentage(self) -> float:
        """Calculate PnL percentage"""
        if self.entry_price == 0:
            return 0.0
        
        if self.side == PositionSide.LONG:
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            return ((self.entry_price - self.current_price) / self.entry_price) * 100

@dataclass
class Order:
    """Represents an order (open or filled)"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None
    filled_size: float = 0.0
    status: str = "open"  # open, filled, cancelled, rejected
    timestamp: Optional[datetime] = None
    trigger_price: Optional[float] = None  # for stop orders
    
    @property
    def is_filled(self) -> bool:
        return self.status == "filled"
    
    @property
    def is_open(self) -> bool:
        return self.status == "open"

@dataclass
class Trade:
    """Represents a completed trade"""
    trade_id: str
    symbol: str
    side: OrderSide
    size: float
    price: float
    timestamp: datetime
    fee: Optional[float] = None
    order_id: Optional[str] = None

@dataclass
class UserState:
    """Represents the complete state of a user's account"""
    address: str
    positions: List[Position]
    orders: List[Order]
    balance: float
    margin_used: float
    unrealized_pnl: float
    timestamp: datetime
    
    @property
    def available_balance(self) -> float:
        """Calculate available balance"""
        return self.balance - self.margin_used
    
    @property
    def total_equity(self) -> float:
        """Calculate total equity (balance + unrealized PnL)"""
        return self.balance + self.unrealized_pnl
    
    @property
    def margin_ratio(self) -> float:
        """Calculate margin ratio"""
        if self.balance == 0:
            return 0.0
        return (self.margin_used / self.balance) * 100

@dataclass
class WebSocketUpdate:
    """Represents a WebSocket update event"""
    channel: str
    data: dict
    timestamp: datetime
