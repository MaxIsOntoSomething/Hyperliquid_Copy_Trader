import asyncio
import json
import websockets
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from loguru import logger
from .models import WebSocketUpdate

class HyperliquidWebSocket:
    """
    WebSocket client for real-time Hyperliquid data
    """
    
    def __init__(self, ws_url: str = "wss://api.hyperliquid.xyz/ws"):
        self.ws_url = ws_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False
        self.reconnect_delay = 5
        self.subscriptions: Dict[str, Any] = {}
        self.callbacks: Dict[str, Callable] = {}
        
    async def connect(self):
        """Establish WebSocket connection"""
        try:
            logger.info(f"Connecting to Hyperliquid WebSocket: {self.ws_url}")
            self.ws = await websockets.connect(self.ws_url)
            self.is_running = True
            logger.info("WebSocket connected successfully")
            
            # Resubscribe to channels after reconnection
            for channel, sub_data in self.subscriptions.items():
                await self._send_subscription(sub_data)
                
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise
    
    async def disconnect(self):
        """Close WebSocket connection"""
        self.is_running = False
        if self.ws:
            await self.ws.close()
            logger.info("WebSocket disconnected")
    
    async def _send_subscription(self, data: dict):
        """Send subscription message"""
        if self.ws:
            try:
                await self.ws.send(json.dumps(data))
                logger.debug(f"Sent subscription: {data}")
            except Exception as e:
                logger.error(f"Failed to send subscription: {e}")
    
    async def subscribe_user(self, address: str, callback: Optional[Callable] = None):
        """
        Subscribe to user updates (positions, orders, fills)
        
        Args:
            address: Wallet address to monitor
            callback: Function to call when updates are received
        """
        channel = f"user:{address}"
        
        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "userEvents",
                "user": address
            }
        }
        
        self.subscriptions[channel] = subscription
        if callback:
            self.callbacks[channel] = callback
        
        if self.ws:
            await self._send_subscription(subscription)
        
        logger.info(f"Subscribed to user updates for {address}")
    
    async def subscribe_trades(self, symbol: str, callback: Optional[Callable] = None):
        """
        Subscribe to trade updates for a specific symbol
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC")
            callback: Function to call when trades are received
        """
        channel = f"trades:{symbol}"
        
        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "trades",
                "coin": symbol
            }
        }
        
        self.subscriptions[channel] = subscription
        if callback:
            self.callbacks[channel] = callback
        
        if self.ws:
            await self._send_subscription(subscription)
        
        logger.info(f"Subscribed to trades for {symbol}")
    
    async def subscribe_all_mids(self, callback: Optional[Callable] = None):
        """
        Subscribe to all mid prices
        
        Args:
            callback: Function to call when price updates are received
        """
        channel = "allMids"
        
        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "allMids"
            }
        }
        
        self.subscriptions[channel] = subscription
        if callback:
            self.callbacks[channel] = callback
        
        if self.ws:
            await self._send_subscription(subscription)
        
        logger.info("Subscribed to all mid prices")
    
    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message"""
        try:
            # Log RAW message
            logger.info(f"📨 RAW WebSocket Message: {message[:500]}...")  # First 500 chars
            
            data = json.loads(message)
            
            # Determine the channel/type of update
            channel = data.get("channel", "unknown")
            
            # Log the parsed data
            logger.info(f"📦 Parsed - Channel: '{channel}', Keys: {list(data.keys())}")
            
            # Create update object
            update = WebSocketUpdate(
                channel=channel,
                data=data,
                timestamp=datetime.utcnow()
            )
            
            # Call appropriate callback
            callback_found = False
            for callback_channel, callback in self.callbacks.items():
                logger.info(f"🔍 Checking callback: {callback_channel} vs {channel}")
                
                # Match logic:
                # 1. Exact match: channel == callback_channel
                # 2. Callback is substring of channel: callback_channel in channel
                # 3. Channel is substring of callback: channel in callback_channel (for "user" matching "user:0x...")
                # 4. Both start with same prefix before colon (for user:address matching user channel)
                should_call = False
                if channel == callback_channel:
                    should_call = True
                elif callback_channel in channel:
                    should_call = True
                elif channel in callback_channel:
                    should_call = True
                elif ":" in callback_channel:
                    # Check if channel matches the prefix (e.g., "user" matches "user:0x...")
                    prefix = callback_channel.split(":")[0]
                    if channel == prefix:
                        should_call = True
                
                if should_call:
                    callback_found = True
                    logger.info(f"✅ Calling callback for {callback_channel}")
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(update)
                        else:
                            callback(update)
                    except Exception as e:
                        logger.error(f"Error in callback for {callback_channel}: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
            
            if not callback_found:
                logger.warning(f"⚠️ No callback found for channel: {channel}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WebSocket message: {e}")
            logger.error(f"Raw message: {message}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def listen(self):
        """
        Main listening loop for WebSocket messages
        Automatically reconnects on connection loss
        """
        while self.is_running:
            try:
                if not self.ws or self.ws.closed:
                    await self.connect()
                
                async for message in self.ws:
                    await self._handle_message(message)
                    
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"WebSocket connection closed, reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
                
            except Exception as e:
                logger.error(f"Error in WebSocket listener: {e}")
                await asyncio.sleep(self.reconnect_delay)
    
    async def run(self):
        """Start the WebSocket connection and listening loop"""
        self.is_running = True
        await self.listen()
    
    async def stop(self):
        """Stop the WebSocket connection"""
        self.is_running = False
        await self.disconnect()
