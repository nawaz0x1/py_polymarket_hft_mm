import asyncio
import logging
import time
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from config import PROFIT_MARGIN, PLACE_OPPOSITE_ORDER
from utils.clob_client import get_client
from utils.trade_counter import decrement_trades
from in_memory_db.utils import contains_item as in_memory_db_contains_item


logger = logging.getLogger(__name__)


async def cache_token_trading_infos(
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


async def place_anchor_and_hedge(
    up_token_id, down_token_id, anchor_side, price, size=5
):
    if anchor_side == "UP":
        anchor_token_id = up_token_id
        hedge_token_id = down_token_id
    else:
        anchor_token_id = down_token_id
        hedge_token_id = up_token_id

    anchor_order_id = await place_limit_order(anchor_token_id, price, size, expire=True)
    if PLACE_OPPOSITE_ORDER and anchor_order_id:
        for _ in range(65 * (1 / 0.02)):
            if in_memory_db_contains_item(anchor_order_id):
                hedge_order_id = await place_limit_order(
                    hedge_token_id, 1 - price - PROFIT_MARGIN, size
                )
                logger.info(
                    f"Order prices: {round(price, 2)} and {round(1 - price - PROFIT_MARGIN, 2)}"
                )
                break
            await asyncio.sleep(0.02)
    else:
        logger.info(f"Order price: {price} [Canceled before hedge placement]")
        decrement_trades()


async def place_limit_order(token_id: str, price: float, size: int, expire=False):
    client = get_client()
    expiration = 0
    if expire:
        one_minute = 60
        desired_seconds = 5
        expiration = int(time.time()) + one_minute + desired_seconds
    try:

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=BUY,
            expiration=expiration,
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(
            signed_order, OrderType.GTD if expire else OrderType.GTC
        )
        logger.info(
            f"Placed limit order: Token ID={token_id}, Price={price}, Size={size}, ID={response['orderID']}"
        )
        return response["orderID"]
    except Exception as e:
        logger.error(f"Error placing order for token {token_id}: {e}")
        return None
