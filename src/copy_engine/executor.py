"""Trade execution engine for Hyperliquid"""
import time
from typing import Optional, Dict, Any
from decimal import Decimal
from eth_account import Account
import aiohttp

from ..utils.logger import logger
from ..hyperliquid.models import OrderType, OrderSide


class TradeExecutor:
    """Executes trades on Hyperliquid exchange"""
    
    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        info_url: str = "https://api.hyperliquid.xyz/info",
        exchange_url: str = "https://api.hyperliquid.xyz/exchange",
        dry_run: bool = True
    ):
        """Initialize trade executor
        
        Args:
            wallet_address: Hyperliquid wallet address
            private_key: Private key for signing transactions
            info_url: Hyperliquid info API URL
            exchange_url: Hyperliquid exchange API URL
            dry_run: If True, simulate orders without executing
        """
        self.wallet_address = wallet_address.lower() if wallet_address else None
        self.private_key = private_key
        self.info_url = info_url
        self.exchange_url = exchange_url
        self.dry_run = dry_run
        
        # Initialize signing account if we have credentials
        self.account = None
        if self.private_key and not self.dry_run:
            try:
                self.account = Account.from_key(self.private_key)
                # Validate address matches
                if self.account.address.lower() != self.wallet_address:
                    raise ValueError(
                        f"Private key address {self.account.address} doesn't match "
                        f"configured address {self.wallet_address}"
                    )
                logger.info(f"✅ Executor initialized for wallet {self.wallet_address}")
            except Exception as e:
                logger.error(f"Failed to initialize signing account: {e}")
                raise
        elif not self.dry_run:
            raise ValueError("Cannot run in live mode without private key")
        else:
            logger.warning("⚠️ Running in DRY RUN mode - no real trades will be executed")
    
    def _sign_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Sign an action using EIP-712 structured data signing
        
        Args:
            action: Action to sign
            
        Returns:
            Signed action with signature
        """
        if not self.account:
            raise ValueError("Cannot sign actions without account")
        
        # Add timestamp nonce
        timestamp = int(time.time() * 1000)
        
        # Create EIP-712 structured data
        structured_data = {
            "domain": {
                "name": "Exchange",
                "version": "1",
                "chainId": 1337,
                "verifyingContract": "0x0000000000000000000000000000000000000000"
            },
            "primaryType": "Agent",
            "types": {
                "Agent": [
                    {"name": "source", "type": "string"},
                    {"name": "connectionId", "type": "bytes32"}
                ],
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ]
            },
            "message": {
                "source": "a",  # "a" indicates API order
                "connectionId": "0x" + "0" * 64
            }
        }
        
        # Sign using sign_typed_data method
        signed_message = self.account.sign_typed_data(
            structured_data["domain"],
            {"Agent": structured_data["types"]["Agent"]},
            structured_data["message"]
        )
        
        # Create signature object
        signature = {
            "r": "0x" + signed_message.r.to_bytes(32, "big").hex(),
            "s": "0x" + signed_message.s.to_bytes(32, "big").hex(),
            "v": signed_message.v
        }
        
        # Build final request
        return {
            "action": action,
            "nonce": timestamp,
            "signature": signature,
            "vaultAddress": None
        }
    
    async def _update_leverage(
        self,
        symbol: str,
        leverage: int,
        is_cross: bool = True
    ) -> bool:
        """Update leverage for a symbol
        
        Args:
            symbol: Trading symbol (e.g. "BTC")
            leverage: Leverage value (integer)
            is_cross: If True, use cross margin. If False, use isolated
            
        Returns:
            True if successful, False otherwise
        """
        try:
            action = {
                "type": "updateLeverage",
                "asset": symbol,
                "isCross": is_cross,
                "leverage": leverage
            }
            
            signed_action = self._sign_action(action)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        await response.json()  # Read response
                        logger.success(f"✅ Updated leverage for {symbol} to {leverage}x")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to update leverage: {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error updating leverage: {e}")
            return False
    
    async def execute_market_order(
        self,
        symbol: str,
        side: OrderSide,
        size: Decimal,
        leverage: int = 1,
        reduce_only: bool = False
    ) -> Optional[str]:
        """Execute a market order
        
        Args:
            symbol: Trading symbol (e.g. "BTC")
            side: Order side (BUY or SELL)
            size: Order size
            leverage: Leverage to use
            reduce_only: If True, order will only reduce position
            
        Returns:
            Order ID if successful, None otherwise
        """
        if self.dry_run:
            return await self._simulate_order(
                symbol=symbol,
                side=side,
                size=size,
                order_type=OrderType.MARKET,
                leverage=leverage
            )
        
        try:
            # Update leverage first if needed
            if leverage > 1:
                await self._update_leverage(symbol, leverage)
            
            # Create market order action (price 0 = market order)
            action = {
                "type": "order",
                "orders": [{
                    "a": self.wallet_address,
                    "b": side == OrderSide.BUY,
                    "p": "0",  # 0 = market order
                    "s": str(float(size)),
                    "r": reduce_only,
                    "t": {"limit": {"tif": "Ioc"}},  # Immediate or Cancel
                    "c": symbol
                }],
                "grouping": "na"
            }
            
            signed_action = self._sign_action(action)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.success(
                            f"✅ Market {side.value} order executed: {symbol} "
                            f"size={size} leverage={leverage}x"
                        )
                        # Extract order ID from response
                        if result.get("status") == "ok" and result.get("response", {}).get("data"):
                            order_id = result["response"]["data"].get("statuses", [{}])[0].get("resting", {}).get("oid")
                            return order_id
                        return "executed"  # Order filled immediately
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to execute market order: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error executing market order: {e}")
            return None
    
    async def execute_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        size: Decimal,
        price: Decimal,
        leverage: int = 1,
        reduce_only: bool = False,
        post_only: bool = False
    ) -> Optional[str]:
        """Execute a limit order
        
        Args:
            symbol: Trading symbol (e.g. "BTC")
            side: Order side (BUY or SELL)
            size: Order size
            price: Limit price
            leverage: Leverage to use
            reduce_only: If True, order will only reduce position
            post_only: If True, order will only add liquidity (maker-only)
            
        Returns:
            Order ID if successful, None otherwise
        """
        if self.dry_run:
            return await self._simulate_order(
                symbol=symbol,
                side=side,
                size=size,
                order_type=OrderType.LIMIT,
                price=price,
                leverage=leverage
            )
        
        try:
            # Update leverage first if needed
            if leverage > 1:
                await self._update_leverage(symbol, leverage)
            
            # Create limit order action
            tif = "Alo" if post_only else "Gtc"  # Alo = Add Liquidity Only, Gtc = Good Till Cancel
            
            action = {
                "type": "order",
                "orders": [{
                    "a": self.wallet_address,
                    "b": side == OrderSide.BUY,
                    "p": str(float(price)),
                    "s": str(float(size)),
                    "r": reduce_only,
                    "t": {"limit": {"tif": tif}},
                    "c": symbol
                }],
                "grouping": "na"
            }
            
            signed_action = self._sign_action(action)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.success(
                            f"✅ Limit {side.value} order placed: {symbol} "
                            f"size={size} price={price} leverage={leverage}x"
                        )
                        # Extract order ID from response
                        if result.get("status") == "ok" and result.get("response", {}).get("data"):
                            order_id = result["response"]["data"].get("statuses", [{}])[0].get("resting", {}).get("oid")
                            return order_id
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to place limit order: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            return None
    
    async def close_position(
        self,
        symbol: str,
        size: Decimal,
        side: OrderSide
    ) -> Optional[str]:
        """Close a position using a market order
        
        Args:
            symbol: Trading symbol
            size: Position size to close
            side: Side to close (opposite of position side)
            
        Returns:
            Order ID if successful, None otherwise
        """
        if self.dry_run:
            logger.info(f"🔵 DRY RUN: Would close {side.value} {size} {symbol}")
            return f"dry_run_close_{symbol}_{int(time.time())}"
        
        return await self.execute_market_order(
            symbol=symbol,
            side=side,
            size=size,
            reduce_only=True
        )
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            logger.info(f"🔵 DRY RUN: Would cancel order {order_id} for {symbol}")
            return True
        
        try:
            action = {
                "type": "cancel",
                "cancels": [{
                    "a": self.wallet_address,
                    "o": order_id
                }]
            }
            
            signed_action = self._sign_action(action)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        logger.success(f"✅ Cancelled order {order_id} for {symbol}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to cancel order: {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all orders
        
        Args:
            symbol: If provided, cancel only orders for this symbol
            
        Returns:
            Number of orders cancelled
        """
        if self.dry_run:
            logger.info(f"🔵 DRY RUN: Would cancel all orders{f' for {symbol}' if symbol else ''}")
            return 0
        
        try:
            action = {
                "type": "cancelByCloid",
                "cancels": [{
                    "asset": symbol if symbol else None,
                    "cloid": None  # Cancel all
                }]
            }
            
            signed_action = self._sign_action(action)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        count = len(result.get("response", {}).get("data", {}).get("statuses", []))
                        logger.success(f"✅ Cancelled {count} orders{f' for {symbol}' if symbol else ''}")
                        return count
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to cancel all orders: {error_text}")
                        return 0
                        
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return 0
    
    async def _simulate_order(
        self,
        symbol: str,
        side: OrderSide,
        size: Decimal,
        order_type: OrderType,
        price: Optional[Decimal] = None,
        leverage: int = 1
    ) -> str:
        """Simulate an order without executing
        
        Args:
            symbol: Trading symbol
            side: Order side
            size: Order size
            order_type: Order type
            price: Order price (for limit orders)
            leverage: Leverage
            
        Returns:
            Simulated order ID
        """
        order_id = f"sim_{symbol}_{int(time.time())}"
        
        if order_type == OrderType.MARKET:
            logger.info(
                f"🔵 DRY RUN: Would execute MARKET {side.value} {symbol} "
                f"size={size} leverage={leverage}x → Order ID: {order_id}"
            )
        else:
            logger.info(
                f"🔵 DRY RUN: Would place LIMIT {side.value} {symbol} "
                f"size={size} price={price} leverage={leverage}x → Order ID: {order_id}"
            )
        
        return order_id
