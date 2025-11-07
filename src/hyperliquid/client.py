import aiohttp
import json
from typing import Optional, List, Dict, Any
from loguru import logger
from .models import Position, Order, UserState, PositionSide, OrderSide

class HyperliquidClient:
    """
    Client for interacting with Hyperliquid REST API
    """
    
    def __init__(self, api_url: str = "https://api.hyperliquid.xyz"):
        self.api_url = api_url
        self.info_url = f"{api_url}/info"
        self.exchange_url = f"{api_url}/exchange"
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _post(self, url: str, data: dict) -> dict:
        """Make POST request to API"""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            async with self.session.post(url, json=data) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"API request failed: {e}")
            raise
    
    async def get_user_state(self, address: str) -> Optional[UserState]:
        """
        Get complete user state including positions and orders
        
        Args:
            address: Wallet address to query
            
        Returns:
            UserState object or None if failed
        """
        try:
            data = {
                "type": "clearinghouseState",
                "user": address
            }
            
            response = await self._post(self.info_url, data)
            
            if not response:
                return None
            
            # Parse positions
            positions = []
            if "assetPositions" in response:
                for pos_data in response["assetPositions"]:
                    position = pos_data.get("position", {})
                    if position and position.get("szi") != "0":  # szi is the position size
                        size = float(position.get("szi", 0))
                        side = PositionSide.LONG if size > 0 else PositionSide.SHORT
                        
                        positions.append(Position(
                            symbol=pos_data.get("coin", ""),
                            side=side,
                            size=abs(size),
                            entry_price=float(position.get("entryPx", 0)),
                            current_price=float(position.get("positionValue", 0)) / abs(size) if size != 0 else 0,
                            leverage=float(position.get("leverage", {}).get("value", 1)),
                            unrealized_pnl=float(position.get("unrealizedPnl", 0)),
                            liquidation_price=float(position.get("liquidationPx")) if position.get("liquidationPx") else None,
                            margin=float(position.get("marginUsed", 0))
                        ))
            
            # Parse orders
            orders = []
            if "openOrders" in response:
                for order_data in response["openOrders"]:
                    order = order_data.get("order", {})
                    orders.append(Order(
                        order_id=str(order.get("oid", "")),
                        symbol=order.get("coin", ""),
                        side=OrderSide.BUY if order.get("side") == "B" else OrderSide.SELL,
                        order_type=order.get("orderType", "limit").lower(),
                        size=float(order.get("sz", 0)),
                        price=float(order.get("limitPx", 0)) if order.get("limitPx") else None,
                        filled_size=float(order.get("szFilled", 0)),
                        status="open",
                        trigger_price=float(order.get("triggerPx", 0)) if order.get("triggerPx") else None
                    ))
            
            # Parse account balance
            balance = float(response.get("marginSummary", {}).get("accountValue", 0))
            margin_used = float(response.get("marginSummary", {}).get("totalMarginUsed", 0))
            unrealized_pnl = float(response.get("marginSummary", {}).get("totalNtlPos", 0))
            
            from datetime import datetime
            return UserState(
                address=address,
                positions=positions,
                orders=orders,
                balance=balance,
                margin_used=margin_used,
                unrealized_pnl=unrealized_pnl,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Failed to get user state for {address}: {e}")
            return None
    
    async def get_all_assets(self) -> List[Dict[str, Any]]:
        """Get list of all available trading assets"""
        try:
            data = {"type": "meta"}
            response = await self._post(self.info_url, data)
            return response.get("universe", [])
        except Exception as e:
            logger.error(f"Failed to get assets: {e}")
            return []
    
    async def get_market_price(self, symbol: str) -> Optional[float]:
        """Get current market price for a symbol"""
        try:
            data = {
                "type": "allMids"
            }
            response = await self._post(self.info_url, data)
            
            # Response is a dict with symbol: price
            if isinstance(response, dict):
                return float(response.get(symbol, 0))
            return None
            
        except Exception as e:
            logger.error(f"Failed to get market price for {symbol}: {e}")
            return None
