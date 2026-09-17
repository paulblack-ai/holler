import asyncio
from genesis import Inbound

async def test():
    client = Inbound('127.0.0.1', 8021, 'ClueCon')
    print('Starting...')
    await asyncio.wait_for(client.start(), timeout=5)
    print('Connected!')
    resp = await asyncio.wait_for(client.send('api status'), timeout=5)
    print(f'Status: {resp}')
    await client.stop()

asyncio.run(test())
