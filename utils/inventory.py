import requests
import os


def get_inventory(slug=None):

    url = f"https://data-api.polymarket.com/positions?sizeThreshold=1&user={os.getenv('POLYMARKET_PROXY_ADDRESS')}&mergeable=false"

    response = requests.get(url).json()
    size = 0
    for pos in response:
        if pos and pos.get("slug") == slug:
            size += pos.get("size")
            print(pos)
    return round(size / 5)
