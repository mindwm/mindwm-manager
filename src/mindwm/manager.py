#!/usr/bin/env python3
import asyncio
from functools import partial
import json
from uuid import uuid4
from pprint import pprint
from decouple import config

from mindwm.modules.nats_interface import NatsInterface
from mindwm.modules.tmux_manager import Tmux_manager
from mindwm.modules.pipe_listener import PipeListener
from mindwm.modules.text_processor import TextProcessor
from mindwm.modules.dbus_interface import DbusInterface


class Manager:
    def __init__(self):
        env = {
            "MINDWM_BACK_NATS_HOST": config("MINDWM_BACK_NATS_HOST", default="127.0.0.1"),
            "MINDWM_BACK_NATS_PORT": config("MINDWM_BACK_NATS_PORT", default=4222, cast=int),
            "MINDWM_BACK_NATS_USER": config("MINDWM_BACK_NATS_USER", default="root"),
            "MINDWM_BACK_NATS_PASS": config("MINDWM_BACK_NATS_PASS", default="r00tpass"),
            "MINDWM_BACK_NATS_SUBJECT_PREFIX": config("MINDWM_BACK_NATS_SUBJECT_PREFIX"),

            "MINDWM_ASCIINEMA_REC_PIPE": config("MINDWM_ASCIINEMA_REC_PIPE"),
        }
        self.params = {
            "asciinema" : {
                "rec_pipe": f"{env['MINDWM_ASCIINEMA_REC_PIPE']}",
            },
            "nats": {
                "url": f"nats://{env['MINDWM_BACK_NATS_USER']}:{env['MINDWM_BACK_NATS_PASS']}@{env['MINDWM_BACK_NATS_HOST']}:{env['MINDWM_BACK_NATS_PORT']}",
                "subject_prefix": f"{env['MINDWM_BACK_NATS_SUBJECT_PREFIX']}",
                "listen": {
                    "feedback": {
                        "subject": f"{env['MINDWM_BACK_NATS_SUBJECT_PREFIX']}.feedback",
                        "callback": self.feedback_callback,
                    },
                    "graph_events": {
                        "subject": "user-root.mindwm-client-broker-kne-trigger._knative",
                        "callback": self.graph_event_callback,
                    },
                    "iodoc_topic": {
                        "subject": "mindwm.root.mindwm-client.tmux.L3RtcC90bXV4LTAvZGVmYXVsdCwyMCww.25a67850-028d-4424-abc6-552fb8ea7775.0.0.test",
                        "callback": self.iodoc_callback,
                    },
                },
            },
        }

    async def init(self):
        # Nats interface
        self._loop = asyncio.get_event_loop()
        self.nats = NatsInterface(self.params['nats']['url'])
        await self.nats.init()
        self._loop.create_task(self.nats.loop())
        for k, v in self.params['nats']['listen'].items():
            await self.nats.subscribe(v['subject'], v['callback'])

        # DBus interface
        self.dbus = DbusInterface()
        self._loop.create_task(self.dbus.init())

        # Pipe listener
        self.pipe_listener = PipeListener(self.params['asciinema']['rec_pipe'], cb=self.input_callback)
        await self.pipe_listener.init()
        self._loop.create_task(self.pipe_listener.loop())

    async def run(self):
        while True:
            await asyncio.sleep(1)

    async def nats_publish(self, topic, t, msg):
        subject = f"{self.params['nats']['subject_prefix']}.{topic}"
        payload = {
            "knativebrokerttl": "255",
            "specversion": "1.0",
            "type": t,
            "source": f"{subject}",
            "subject": f"{subject}",
            "datacontenttype": "application/json",
            "data": {
                t: msg,
            },
            "id": str(uuid4()),
        }
        await self.nats.publish(subject, bytes(json.dumps(payload), encoding='utf-8'))

    async def input_callback(self, payload):
        result = json.loads(payload)
        print(f"iodocument: {payload}")
        await self.nats_publish("iodocument", "iodocument", result)

    async def graph_event_callback(self, msg):
        print(f"graph event received: {msg}")
    
    async def feedback_callback(self, msg):
        print(f"feedback received: {msg}")
    
    async def iodoc_callback(self, msg):
        print(f"iodoc received: {msg}")


async def app():
    mgr = Manager()
    await mgr.init()
    await mgr.run()

if __name__ == "__main__":
    asyncio.run(app())
