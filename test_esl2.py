import asyncio
import os

os.environ['HOLLER_ESL_HOST_PORT'] = '18021'

from holler.core.freeswitch.esl import FreeSwitchESL

async def test():
    async with FreeSwitchESL() as esl:
        print("ESL connected and verified UP")

asyncio.run(test())
