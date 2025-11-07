import asyncio
from typing import Callable, Optional, List
from loguru import logger
from ..hyperliquid.client import HyperliquidClient
from ..hyperliquid.websocket import HyperliquidWebSocket
from ..hyperliquid.models import Position, Order, UserState, WebSocketUpdate


class WalletMonitor:
    """
    Monitor a target wallet for trading activity
    """
    
    def __init__(
        self,
        target_address: str,
        api_url: str = "https://api.hyperliquid.xyz",
        ws_url: str = "wss://api.hyperliquid.xyz/ws"
    ):
        self.target_address = target_address
        self.client = HyperliquidClient(api_url)
        self.ws = HyperliquidWebSocket(ws_url)
        
        # Current state tracking
        self.current_state: Optional[UserState] = None
        self.last_positions: List[Position] = []
        self.last_orders: List[Order] = []
        
        # Callbacks
        self.on_new_position: Optional[Callable] = None
        self.on_position_update: Optional[Callable] = None
        self.on_position_close: Optional[Callable] = None
        self.on_new_order: Optional[Callable] = None
        self.on_order_fill: Optional[Callable] = None
        self.on_order_cancel: Optional[Callable] = None
        
        logger.info(f"Wallet Monitor initialized for {target_address}")
    
    async def get_current_state(self) -> Optional[UserState]:
        """Fetch current state of target wallet"""
        async with self.client:
            self.current_state = await self.client.get_user_state(self.target_address)
            
            if self.current_state:
                self.last_positions = self.current_state.positions.copy()
                self.last_orders = self.current_state.orders.copy()
            
            return self.current_state
    
    async def start_monitoring(self):
        """Start monitoring the target wallet"""
        logger.info(f"Starting monitoring for {self.target_address}")
        
        # Get initial state
        await self.get_current_state()
        
        # Connect WebSocket
        await self.ws.connect()
        
        # Subscribe to user updates
        await self.ws.subscribe_user(self.target_address, self._handle_update)
        
        # Start listening
        await self.ws.listen()
    
    async def stop_monitoring(self):
        """Stop monitoring"""
        logger.info("Stopping wallet monitoring")
        await self.ws.stop()
    
    async def _handle_update(self, update: WebSocketUpdate):
        """Handle WebSocket updates from target wallet"""
        logger.info(f"🔔 WebSocket Update Received: {update.channel}")
        
        try:
            if "data" not in update.data:
                logger.warning(f"⚠️ Update has no 'data' field: {update.data}")
                return
            
            data = update.data["data"]
            logger.info(f"📦 Update data keys: {list(data.keys())}")
            
            # Handle fills (completed trades)
            if "fills" in data:
                logger.success(f"💥 FILLS DETECTED: {len(data['fills'])} fills")
                await self._handle_fills(data["fills"])
            
            # Handle position updates
            if "positions" in data:
                logger.success(f"📊 POSITIONS UPDATE: {len(data['positions'])} positions")
                await self._handle_positions(data["positions"])
            
            # Handle order updates
            if "orders" in data:
                logger.success(f"📋 ORDERS UPDATE: {len(data['orders'])} orders")
                await self._handle_orders(data["orders"])
                
        except Exception as e:
            logger.error(f"Error handling update: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _handle_fills(self, fills: List[dict]):
        """Handle trade fills"""
        for fill in fills:
            # Extract symbol from fill data
            symbol = fill.get("coin", "").upper()
            
            # Check if asset is blocked
            from ..config.settings import settings
            if symbol in settings.copy_rules.blocked_assets:
                logger.warning(f"⛔ BLOCKED ASSET - Ignoring fill for {symbol} (in blocked list)")
                continue
            
            logger.success(f"🎯 FILL DETECTED: {fill}")
            
            if self.on_order_fill:
                try:
                    if asyncio.iscoroutinefunction(self.on_order_fill):
                        await self.on_order_fill(fill)
                    else:
                        self.on_order_fill(fill)
                except Exception as e:
                    logger.error(f"Error in fill callback: {e}")
    
    async def _handle_positions(self, positions: List[dict]):
        """Handle position updates"""
        logger.info(f"📍 Position update received: {len(positions)} positions")
        
        from ..config.settings import settings
        
        for pos_data in positions:
            # Parse position data
            symbol = pos_data.get("coin", "").upper()
            size = float(pos_data.get("szi", 0))
            
            # Check if asset is blocked
            if symbol in settings.copy_rules.blocked_assets:
                logger.debug(f"⛔ Ignoring position update for blocked asset: {symbol}")
                continue
            
            # Check if this is a new position
            existing = next((p for p in self.last_positions if p.symbol == symbol), None)
            
            if not existing and size != 0:
                # NEW POSITION!
                logger.success(f"🆕 NEW POSITION DETECTED: {symbol}")
                
                if self.on_new_position:
                    try:
                        if asyncio.iscoroutinefunction(self.on_new_position):
                            await self.on_new_position(pos_data)
                        else:
                            self.on_new_position(pos_data)
                    except Exception as e:
                        logger.error(f"Error in new position callback: {e}")
            
            elif existing and size == 0:
                # POSITION CLOSED
                logger.info(f"❌ POSITION CLOSED: {symbol}")
                
                if self.on_position_close:
                    try:
                        if asyncio.iscoroutinefunction(self.on_position_close):
                            await self.on_position_close(pos_data)
                        else:
                            self.on_position_close(pos_data)
                    except Exception as e:
                        logger.error(f"Error in position close callback: {e}")
            
            elif existing and abs(size) != abs(existing.size):
                # POSITION SIZE CHANGED
                logger.info(f"📊 POSITION UPDATED: {symbol} ({existing.size} -> {size})")
                
                if self.on_position_update:
                    try:
                        if asyncio.iscoroutinefunction(self.on_position_update):
                            await self.on_position_update(pos_data)
                        else:
                            self.on_position_update(pos_data)
                    except Exception as e:
                        logger.error(f"Error in position update callback: {e}")
        
        # Update state
        await self.get_current_state()
    
    async def _handle_orders(self, orders: List[dict]):
        """Handle order updates"""
        logger.info(f"📝 Order update received: {len(orders)} orders")
        
        for order_data in orders:
            order_id = str(order_data.get("oid", ""))
            symbol = order_data.get("coin", "")
            
            # Check if new order
            existing = next((o for o in self.last_orders if o.order_id == order_id), None)
            
            if not existing:
                logger.success(f"📋 NEW ORDER: {symbol} - ID: {order_id}")
                
                if self.on_new_order:
                    try:
                        if asyncio.iscoroutinefunction(self.on_new_order):
                            await self.on_new_order(order_data)
                        else:
                            self.on_new_order(order_data)
                    except Exception as e:
                        logger.error(f"Error in new order callback: {e}")
        
        # Update state
        await self.get_current_state()
