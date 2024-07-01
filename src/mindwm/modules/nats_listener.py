import asyncio
import nats
import json


class NatsListener:
    def __init__(self, url, feedback_subject, message_callback=None):
        self.url = url
        self.feedback_subject = feedback_subject
        self.message_callback = message_callback
        self._loop = asyncio.get_event_loop()

    async def init(self):
        print(f"Initializing NATS listener:\n\t{self.url}\n\t{self.feedback_subject}")
        await self.connect()
        await self.listen()
        # TODO: need to catch a signals about connection state
        await asyncio.Future()
        await self.nc.close()

    async def connect(self):
        self.nc = await nats.connect(self.url)

    async def listen(self):
        self.sub = await self.nc.subscribe(self.feedback_subject, cb=self.message_handler)

    async def message_handler(self, msg):
        data = json.loads(msg.data.decode())
        message = data['message']

        if self.message_callback:
            await self.message_callback(message)
