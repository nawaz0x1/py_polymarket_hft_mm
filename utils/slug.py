import pytz
from datetime import datetime
from config import MARKET_SESSION_SECONDS, TIMEZONE


def get_market_slug(coin: str = "btc") -> str:

    if not coin or not isinstance(coin, str):
        raise ValueError("Coin must be a non-empty string")

    et_tz = pytz.timezone(TIMEZONE)
    now = datetime.now(et_tz)
    ts = int(now.timestamp())
    start = (ts // MARKET_SESSION_SECONDS) * MARKET_SESSION_SECONDS
    return f"{coin.lower()}-updown-15m-{start}"
