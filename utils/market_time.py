import time
from config import MARKET_SESSION_SECONDS


def get_period_elapsed_seconds():
    ts = int(time.time())
    period_start = (ts // MARKET_SESSION_SECONDS) * MARKET_SESSION_SECONDS
    return ts - period_start


def is_in_trading_window():
    elapsed_seconds = get_period_elapsed_seconds()
    return elapsed_seconds < (MARKET_SESSION_SECONDS - 5)
