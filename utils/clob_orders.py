import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from config import PROFIT_MARGIN, PLACE_OPPOSITE_ORDER
from utils.clob_client import get_client
from utils.trade_counter import decrement_trades


logger = logging.getLogger(__name__)


def cache_token_trading_infos(
    order_book,
) -> None:
    client = get_client()

    up_token_id, down_token_id = order_book.up_token_id, order_book.down_token_id
    client.get_tick_size(up_token_id)
    client.get_tick_size(down_token_id)
    client.get_neg_risk(up_token_id)
    client.get_neg_risk(down_token_id)
    client.get_fee_rate_bps(up_token_id)
    client.get_fee_rate_bps(down_token_id)


def place_anchor_and_hedge(
    up_token_id, down_token_id, anchor_side, price, size=5, signed_orders_cache=None
):
    if anchor_side == "UP":
        anchor_token_id = up_token_id
        hedge_token_id = down_token_id
    else:
        anchor_token_id = down_token_id
        hedge_token_id = up_token_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(
            place_limit_order_sync,
            anchor_token_id,
            price,
            size,
            signed_orders_cache,
        )
        future2 = executor.submit(
            place_limit_order_sync,
            hedge_token_id,
            round(1 - price - PROFIT_MARGIN, 2),
            size,
            signed_orders_cache,
        )
        
        # Wait for both to complete
        order_ids = [future1.result(), future2.result()]

    logger.info(
        f"Placed anchor and hedge orders: Anchor Token ID={anchor_token_id}, Hedge Token ID={hedge_token_id}, Order IDs={order_ids}"
    )
    return order_ids


def place_limit_order_sync(
    token_id: str, price: float, size: int = 5, signed_orders_cache=None
) -> str:
    """Synchronous version of place_limit_order for use with ThreadPoolExecutor"""
    client = get_client()

    try:
        if signed_orders_cache and (token_id, price) in signed_orders_cache:
            signed_order = signed_orders_cache[(token_id, price)]
            logger.info(
                f"Using cached signed order for Token ID={token_id}, Price={price}"
            )
        else:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=BUY,
            )
            signed_order = client.create_order(order_args)
        response = client.post_order(signed_order)
        logger.info(
            f"Placed limit order: Token ID={token_id}, Price={price}, Size={size}, ID={response['orderID']}"
        )
        return response["orderID"]
    except Exception as e:
        logger.error(f"Error placing order for token {token_id}: {e}")
        return None



