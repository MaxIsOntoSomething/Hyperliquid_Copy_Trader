import json
import time
from typing import Optional, Dict, Any
from eth_account import Account
from eth_account.signers.local import LocalAccount
from loguru import logger

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info


class TradeExecutor:
    """
    Execute trades on your Hyperliquid account using the official SDK
    """
    
    def __init__(
        self,
        api_url: str = "https://api.hyperliquid.xyz",
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
        dry_run: bool = True
    ):
        """
        Initialize trade executor
        
        Args:
            api_url: Hyperliquid API URL
            wallet_address: Your wallet address (not used if SDK is used)
            private_key: Your private key for signing
            dry_run: If True, only simulate trades without executing
        """
        self.api_url = api_url
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.dry_run = dry_run
        
        # Initialize Hyperliquid Exchange and Info if credentials provided
        self.account: Optional[LocalAccount] = None
        self.exchange: Optional[Exchange] = None
        self.info: Optional[Info] = None
        
        if private_key and not dry_run:
            try:
                self.account = Account.from_key(private_key)
                self.exchange = Exchange(self.account, base_url=api_url)
                self.info = Info(base_url=api_url, skip_ws=True)
                logger.info(f"✅ Executor initialized for wallet: {self.account.address}")
                logger.info("🚀 LIVE TRADING MODE - Real orders will be placed!")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Hyperliquid SDK: {e}")
                raise
        elif not dry_run:
            logger.error("❌ Cannot enable live trading without private key!")
            raise ValueError("Private key required for live trading")
        
        if dry_run:
            logger.warning("⚠️ DRY RUN MODE - Trades will be simulated, not executed!")
    
    async def execute_market_order(
        self,
        symbol: str,
        side: str,  # "LONG" or "SHORT"
        size: float,
        leverage: int,
        reduce_only: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Execute a market order"""
        try:
            is_buy = side == "LONG"
            
            logger.info(f"{'📊 Simulating' if self.dry_run else '💰 Executing'} market order: "
                       f"{symbol} {side} size={size} leverage={leverage}x")
            
            if self.dry_run:
                return self._simulate_order(symbol, side, size, leverage, "market", 0, reduce_only)
            
            # LIVE TRADING - Use Hyperliquid SDK
            if not self.exchange or not self.info:
                logger.error("❌ Exchange not initialized for live trading")
                return None
            
            # Set leverage before placing order
            try:
                leverage_result = self.exchange.update_leverage(leverage, symbol, is_cross=True)
                logger.debug(f"Leverage set result: {leverage_result}")
            except Exception as e:
                logger.warning(f"Failed to set leverage: {e}")
            
            # Use market_open with slippage tolerance
            # Market orders in Hyperliquid are aggressive IoC limit orders
            slippage = 0.03  # 3% slippage tolerance
            
            result = self.exchange.market_open(
                symbol,
                is_buy,
                size,
                slippage=slippage
            )
            
            if result.get("status") == "ok":
                logger.success(f"✅ Market order executed successfully for {symbol}")
                logger.debug(f"Response: {json.dumps(result, indent=2)}")
                
                # Parse result
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    if "filled" in status:
                        filled = status["filled"]
                        return {
                            "success": True,
                            "order_id": filled.get("oid"),
                            "symbol": symbol,
                            "side": side,
                            "size": filled.get("totalSz"),
                            "price": filled.get("avgPx"),
                            "type": "market"
                        }
                    elif "error" in status:
                        logger.error(f"❌ Order error: {status['error']}")
                        return None
            else:
                logger.error(f"❌ Order failed: {result}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Market order execution failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def execute_limit_order(
        self,
        symbol: str,
        side: str,  # "LONG" or "SHORT"
        size: float,
        price: float,
        leverage: int,
        reduce_only: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Execute a limit order"""
        try:
            is_buy = side == "LONG"
            
            logger.info(f"{'📊 Simulating' if self.dry_run else '💰 Executing'} limit order: "
                       f"{symbol} {side} size={size} @ ${price} leverage={leverage}x")
            
            if self.dry_run:
                return self._simulate_order(symbol, side, size, leverage, "limit", price, reduce_only)
            
            # LIVE TRADING - Use Hyperliquid SDK
            if not self.exchange or not self.info:
                logger.error("❌ Exchange not initialized for live trading")
                return None
            
            # Set leverage before placing order
            try:
                leverage_result = self.exchange.update_leverage(leverage, symbol, is_cross=True)
                logger.debug(f"Leverage set result: {leverage_result}")
            except Exception as e:
                logger.warning(f"Failed to set leverage: {e}")
            
            # Place limit order with GTC (Good Till Cancelled)
            result = self.exchange.order(
                symbol,
                is_buy,
                size,
                price,
                {"limit": {"tif": "Gtc"}},
                reduce_only=reduce_only
            )
            
            if result.get("status") == "ok":
                logger.success(f"✅ Limit order placed successfully for {symbol}")
                logger.debug(f"Response: {json.dumps(result, indent=2)}")
                
                # Parse result
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    if "resting" in status:
                        resting = status["resting"]
                        return {
                            "success": True,
                            "order_id": resting.get("oid"),
                            "symbol": symbol,
                            "side": side,
                            "size": size,
                            "price": price,
                            "type": "limit"
                        }
                    elif "filled" in status:
                        filled = status["filled"]
                        return {
                            "success": True,
                            "order_id": filled.get("oid"),
                            "symbol": symbol,
                            "side": side,
                            "size": filled.get("totalSz"),
                            "price": filled.get("avgPx"),
                            "type": "limit"
                        }
                    elif "error" in status:
                        logger.error(f"❌ Order error: {status['error']}")
                        return None
            else:
                logger.error(f"❌ Order failed: {result}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Limit order execution failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def close_position(
        self,
        symbol: str,
        side: str,  # Current position side "LONG" or "SHORT"
        size: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Close an existing position"""
        try:
            logger.info(f"{'📊 Simulating' if self.dry_run else '💰 Executing'} position close: "
                       f"{symbol} {side}")
            
            if self.dry_run:
                return {
                    "success": True,
                    "symbol": symbol,
                    "side": "LONG" if side == "SHORT" else "SHORT",  # Opposite side to close
                    "size": size if size else 0,
                    "type": "market_close",
                    "simulated": True
                }
            
            # LIVE TRADING - Use Hyperliquid SDK
            if not self.exchange or not self.info:
                logger.error("❌ Exchange not initialized for live trading")
                return None
            
            # Use market_close with slippage tolerance
            slippage = 0.03  # 3% slippage tolerance
            
            result = self.exchange.market_close(
                symbol,
                sz=size,  # If None, closes entire position
                slippage=slippage
            )
            
            if result.get("status") == "ok":
                logger.success(f"✅ Position closed successfully for {symbol}")
                logger.debug(f"Response: {json.dumps(result, indent=2)}")
                
                # Parse result
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    if "filled" in status:
                        filled = status["filled"]
                        return {
                            "success": True,
                            "order_id": filled.get("oid"),
                            "symbol": symbol,
                            "size": filled.get("totalSz"),
                            "price": filled.get("avgPx"),
                            "type": "market_close"
                        }
                    elif "error" in status:
                        logger.error(f"❌ Close error: {status['error']}")
                        return None
            else:
                logger.error(f"❌ Close failed: {result}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Position close failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def cancel_order(
        self,
        symbol: str,
        order_id: int
    ) -> Optional[Dict[str, Any]]:
        """Cancel an open order"""
        try:
            logger.info(f"{'📊 Simulating' if self.dry_run else '💰 Executing'} order cancel: "
                       f"{symbol} order_id={order_id}")
            
            if self.dry_run:
                return {
                    "success": True,
                    "symbol": symbol,
                    "order_id": order_id,
                    "cancelled": True,
                    "simulated": True
                }
            
            # LIVE TRADING - Use Hyperliquid SDK
            if not self.exchange:
                logger.error("❌ Exchange not initialized for live trading")
                return None
            
            result = self.exchange.cancel(symbol, order_id)
            
            if result.get("status") == "ok":
                logger.success(f"✅ Order cancelled successfully for {symbol}")
                logger.debug(f"Response: {json.dumps(result, indent=2)}")
                return {
                    "success": True,
                    "symbol": symbol,
                    "order_id": order_id,
                    "cancelled": True
                }
            else:
                logger.error(f"❌ Cancel failed: {result}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Order cancel failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _simulate_order(
        self,
        symbol: str,
        side: str,
        size: float,
        leverage: int,
        order_type: str,
        price: float = 0,
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """Simulate an order for dry run mode"""
        simulated_price = price if price > 0 else 50000  # Mock price
        
        return {
            "success": True,
            "order_id": f"SIM_{int(time.time())}",
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": simulated_price,
            "leverage": leverage,
            "type": order_type,
            "reduce_only": reduce_only,
            "simulated": True,
            "timestamp": int(time.time())
        }
