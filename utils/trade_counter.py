# Global trades counter
_trades = 0


def get_trades_count():
    return _trades


def increment_trades():
    global _trades
    _trades += 1
    return _trades


def decrement_trades():
    global _trades
    _trades -= 1
    return _trades


def reset_trades():
    global _trades
    _trades = 0
