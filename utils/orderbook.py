import os
import bisect
import time
import json
import logging
import threading
import websocket
from enum import Enum
from config import POLYMARKET_WS_MARKET_URL, TRADING_BPS_THRESHOLD
from py_clob_client import OrderArgs
from py_clob_client.order_builder.constants import BUY
from utils.clob_client import get_client
from utils.inventory import get_inventory

logger = logging.getLogger(__name__)


class SIGNALES(Enum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


class OrderBook:
    def __init__(self, up_token_id: str, down_token_id: str, slug: str):
        self.up_token_id = up_token_id
        self.down_token_id = down_token_id
        self.slug = slug
        self.ws_url = POLYMARKET_WS_MARKET_URL
        self.client = get_client()

        self.orderbook = {
            "best_bid": 0.0,
            "best_ask": 0.0,
            "last_update": None,
            "order_book": {"bids": [], "asks": []},
        }

        self.signed_orders_cache = {}

        self.ws = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        self.monitoring_thread = None
        self.monitoring_running = False

        self.last_signal = SIGNALES.NEUTRAL
        self.inventory = 0
        self.inventory_thread = None
        self.inventory_running = False
        self.create_signed_orders_cache()

    def _on_message(self, ws, message):

        try:
            data = json.loads(message)
            event_type = data.get("event_type")

            if event_type == "book":
                self._update_order_book_snapshot(data)
            elif event_type == "price_change":
                self._process_price_change(data)

        except Exception as e:
            logger.error(f"⚠️  Error processing WebSocket message: {e}")

    def _on_error(self, ws, error):
        logger.error(f"⚠️  WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info("🔌 WebSocket disconnected")

        if self.running:
            logger.info("🔄 Attempting reconnect...")
            threading.Timer(0.1, self._connect).start()

    def _on_open(self, ws):
        logger.info("✅ WebSocket connected - Streaming prices for UP token only")
        payload = {"type": "market", "assets_ids": [self.up_token_id]}
        ws.send(json.dumps(payload))

    def _connect(self):
        if not self.running:
            return

        try:
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )

            self.ws.run_forever()

        except Exception as e:
            logger.error(f"❌ WebSocket connection error: {e}")
            if self.running:
                threading.Timer(0.1, self._connect).start()

    def start(self):
        if self.running:
            logger.warning("⚠️  Price stream already running")
            return

        self.running = True
        self.monitoring_running = True
        self.inventory_running = True

        self.thread = threading.Thread(target=self._connect, daemon=True)
        self.thread.start()

        self.monitoring_thread = threading.Thread(
            target=self._continuous_trading_monitor, daemon=True
        )
        self.monitoring_thread.start()

        self.inventory_thread = threading.Thread(
            target=self._inventory_updater, daemon=True
        )
        self.inventory_thread.start()

        logger.info(
            "WebSocket price stream, trading monitor, and inventory updater started"
        )

    def stop(self):
        self.running = False
        self.monitoring_running = False
        self.inventory_running = False

        if self.ws:
            self.ws.close()

        logger.info(
            "🛑 WebSocket price stream, trading monitor, and inventory updater stopped"
        )

    def _inventory_updater(self):
        logger.info("Started inventory updater thread")
        while self.inventory_running:
            try:
                self.inventory = get_inventory(self.slug)
            except Exception as e:
                logger.error(f"Error updating inventory: {e}")
            time.sleep(1)
        logger.info("Stopped inventory updater thread")

    def is_connected(self):
        with self.lock:
            return self.orderbook["last_update"] is not None

    def get_current_market_data(self):
        if self.orderbook["last_update"] is None:
            return None

        orderbook = self.orderbook["order_book"]
        bids = []
        asks = []

        for bid in orderbook.get("bids", []):
            if isinstance(bid, dict):
                bids.append([float(bid["price"]), float(bid["size"])])
            else:
                bids.append([float(bid[0]), float(bid[1])])

        for ask in orderbook.get("asks", []):
            if isinstance(ask, dict):
                asks.append([float(ask["price"]), float(ask["size"])])
            else:
                asks.append([float(ask[0]), float(ask[1])])

        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        if not bids or not asks:
            return None

        best_bid_price = bids[0][0]
        best_bid_volume = bids[0][1]
        best_ask_price = asks[0][0]
        best_ask_volume = asks[0][1]

        # Calculate micro-price
        total_volume = best_bid_volume + best_ask_volume
        if total_volume > 0:
            micro_price = (
                (best_bid_price * best_ask_volume) + (best_ask_price * best_bid_volume)
            ) / total_volume
        else:
            micro_price = (best_bid_price + best_ask_price) / 2

        mid_price = (best_bid_price + best_ask_price) / 2
        micro_vs_mid_bps = (micro_price - mid_price) * 10000

        return {
            "best_bid_price": best_bid_price,
            "best_ask_price": best_ask_price,
            "micro_price": micro_price,
            "mid_price": mid_price,
            "micro_vs_mid_bps": micro_vs_mid_bps,
            "bids": bids,
            "asks": asks,
        }

    def _continuous_trading_monitor(self):
        logger.info("Started continuous trading monitor")

        while self.monitoring_running:
            try:
                market_data = self.get_current_market_data()
                if not market_data:
                    time.sleep(0.1)
                    continue

                micro_vs_mid_bps = market_data["micro_vs_mid_bps"]

                current_signal = None
                if micro_vs_mid_bps > TRADING_BPS_THRESHOLD:
                    current_signal = SIGNALES.UP
                elif micro_vs_mid_bps < -TRADING_BPS_THRESHOLD:
                    current_signal = SIGNALES.DOWN
                else:
                    current_signal = SIGNALES.NEUTRAL

                if current_signal and current_signal != self.last_signal:
                    self.last_signal = current_signal

                time.sleep(0.005)

            except Exception as e:
                logger.error(f"Error in continuous trading monitor: {e}")
                time.sleep(1)

        logger.info("Stopped continuous trading monitor")

    def create_signed_orders_cache(self):
        start = time.time()
        prices = [0.01]
        while prices[-1] < 0.99:
            prices.append(round(prices[-1] + 0.01, 2))

        client = get_client()
        for price in prices:
            for token_id in [self.up_token_id, self.down_token_id]:
                order_args = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=5,
                    side=BUY,
                )
                signed_order = client.create_order(order_args)
                self.signed_orders_cache[(token_id, price)] = signed_order
        end = time.time()
        logger.info(
            f"Pre-created signed orders cache for tokens in {round((end - start) * 1000)} milliseconds"
        )

    def update_signed_orders_cache(self, prices):
        client = get_client()
        for price in prices:
            for token_id in [self.up_token_id, self.down_token_id]:
                order_args = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=5,
                    side=BUY,
                )
                signed_order = client.create_order(order_args)
                self.signed_orders_cache[(token_id, price)] = signed_order
        logger.info(f"Updated signed orders cache for new prices: {prices}")

    def clear_screen(self):
        os.system("cls" if os.name == "nt" else "clear")

    def _update_order_book_snapshot(self, new_orderbook):
        asset_id = new_orderbook.get("asset_id")

        # Only process UP token as down token is just the opposite side
        if asset_id != self.up_token_id:
            return

        with self.lock:
            self.orderbook["best_bid"] = (
                new_orderbook["bids"][-1]["price"] if new_orderbook["bids"] else 0.0
            )
            self.orderbook["best_ask"] = (
                new_orderbook["asks"][-1]["price"] if new_orderbook["asks"] else 0.0
            )

            self.orderbook["order_book"]["bids"] = new_orderbook.get("bids", [])
            self.orderbook["order_book"]["asks"] = new_orderbook.get("asks", [])
            self.orderbook["last_update"] = time.time()

    def _update_orderbook_incremental(self, asset_id, update):
        if asset_id != self.up_token_id:
            return

        price = float(update["price"])
        side = update["side"]
        size = float(update["size"])

        self.orderbook["best_bid"] = float(update["best_bid"])
        self.orderbook["best_ask"] = float(update["best_ask"])

        orderbook = self.orderbook["order_book"]
        book_side = orderbook["bids"] if side == "BUY" else orderbook["asks"]

        if book_side and isinstance(book_side[0], dict):
            book_side = [
                [float(item["price"]), float(item["size"])] for item in book_side
            ]
            if side == "BUY":
                orderbook["bids"] = book_side
            else:
                orderbook["asks"] = book_side

        idx = bisect.bisect_left(book_side, [price, 0])

        if idx < len(book_side) and book_side[idx][0] == price:
            if size == 0:
                del book_side[idx]
            else:
                book_side[idx][1] = size
        elif size > 0:
            book_side.insert(idx, [price, size])

        if size > 0:
            if side == "BUY":
                asks = orderbook["asks"]
                if asks and isinstance(asks[0], dict):
                    asks = [
                        [float(item["price"]), float(item["size"])] for item in asks
                    ]
                    orderbook["asks"] = asks
                cull_idx = bisect.bisect_right(asks, [price, float("inf")])
                orderbook["asks"] = asks[cull_idx:]
            else:  # side == "SELL"
                bids = orderbook["bids"]
                if bids and isinstance(bids[0], dict):
                    bids = [
                        [float(item["price"]), float(item["size"])] for item in bids
                    ]
                    orderbook["bids"] = bids
                cull_idx = bisect.bisect_left(bids, [price, 0])
                orderbook["bids"] = bids[:cull_idx]

    def _process_price_change(self, data):
        price_changes = data.get("price_changes", [])

        for change in price_changes:
            asset_id = change.get("asset_id")
            if asset_id != self.up_token_id:
                continue

            with self.lock:
                self._update_orderbook_incremental(asset_id, change)
                self.orderbook["last_update"] = time.time()
