import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

async def test():
    return


loop = asyncio.get_event_loop()

times = []

for _ in range(1000):
    start = time.time()
    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [
            loop.run_in_executor(executor, test),
            loop.run_in_executor(
                executor,
                test,
            ),
        ]
    await asyncio.gather(*tasks)

    end = time.time()
    times.append(end - start)



sum(times) 