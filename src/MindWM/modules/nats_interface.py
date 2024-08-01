import logging
from opentelemetry import trace
from datetime import datetime

import asyncio
from functools import partial
import nats
import json
from time import sleep

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class NatsInterface:
    def __init__(self, url):
        self.nc = None
        self.url = url
        self.subs = {}

    async def _init(self):
        logger.info(f"Initializing NATSListener for {self.url}")
        await self.connect()

    async def loop(self):
        logger.debug(f"Entering main NatsInterface loop")

        # TODO: need to catch a signals about connection state
        await asyncio.Future()
        await self.nc.close()

    async def connect(self):
        if not self.nc:
            self.nc = await nats.connect(self.url)
            logger.info(f"Connected to {self.url}")
        else:
            logger.info("already connected")

    async def subscribe(self, subj, callback):
        self.subs[subj] = {}
        handler = partial(self.message_handler, subj, callback)
        await self.nc.subscribe(subj, cb=handler)
        logger.info(f"Subscribed to NATS subject: {subj}")

    async def publish(self, subj, payload):
        with tracer.start_as_current_span("publish") as span:
            ctx = span.get_span_context()
            traceId = ("%0.2X" % ctx.trace_id).lower()
            spanId = ("%0.2X" % ctx.span_id).lower()
            headers = {}
            payload.traceparent = f"00-{traceId}-{spanId}-01"
#            headers = {
#                "TraceId": traceId,
#                "SpanId": spanId,
#            }
            logger.debug(f"send message to {subj}: {payload}")
            await self.nc.publish(subj, bytes(payload.to_json(), encoding='utf-8'), headers=headers)

    async def message_handler(self, subj, callback, msg):
        data = json.loads(msg.data.decode())
        if 'message' in data.keys():
            message = data['message']
        else:
            message = data

        if callback:
            await callback(message)

async def app():
    loop = asyncio.get_event_loop()
    n = NatsInterface("nats://root:r00tpass@10.20.30.211:31109/")
    await n.init()
    loop.create_task(n.loop())

    async def nats_message_callback(msg):
        logger.debug(msg)

    nats_iodoc_topic = "mindwm.root.mindwm-client.tmux.L3RtcC90bXV4LTAvZGVmYXVsdCwyMCww.25a67850-028d-4424-abc6-552fb8ea7775.0.0.test"
    nats_iodoc_topic2 = "mindwm.root.mindwm-client.tmux.L3RtcC90bXV4LTAvZGVmYXVsdCwyMCww.25a67850-028d-4424-abc6-552fb8ea7775.0.0.test2"
    await n.listen(nats_iodoc_topic, nats_message_callback)
    await n.listen(nats_iodoc_topic2, nats_message_callback)


    while True:
        await asyncio.sleep(1)

    logger.info("Done")

if __name__ == "__main__":
    asyncio.run(app())
