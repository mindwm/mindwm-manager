#!/usr/bin/env python3
import asyncio
from functools import partial
import json
from uuid import uuid4
from pprint import pprint
from decouple import config
from base64 import b64encode
from uuid import uuid4
from mindwm.modules.nats_interface import NatsInterface
from mindwm.modules.tmux_manager import Tmux_manager
from mindwm.modules.pipe_listener import PipeListener
from mindwm.modules.text_processor import TextProcessor
from mindwm.modules.dbus_interface import DbusInterface
from mindwm.modules.surrealdb_interface import SurrealDbInterface


class Manager:
    def __init__(self):
        env = {
                "MINDWM_NATS_URL": config("MINDWM_NATS_URL", default="nats://user:pass@127.0.0.1/"),
            #"MINDWM_ASCIINEMA_REC_PIPE": config("MINDWM_ASCIINEMA_REC_PIPE"),
        }
        self.params = {
            "nats": {
                "url": config("MINDWM_NATS_URL", default="nats://user:pass@127.0.0.1/"),
                "subject_prefix": config("MINDWM_NATS_SUBJECT_PREFIX", default=f"mindwm.demouser.demohost"),
                "feeback_subject_suffix": config("MINDWM_NATS_FEEDBACK_SUBJECT_SUFFIX", default="feedback"),
                "graph_events_subject": config("MINDWM_NATS_GRAPH_EVENTS_SUBJECT", default=f"user-demouser.demohost-broker-kne-trigger._knative"),
                "listen": {},
            },
            "surrealdb": {
                "url": config("MINDWM_SURREALDB_URL", default="ws://localhost:8000/mindwm/context_graph"),
            },
        }
        self.params['nats']['listen'] = {
            "graph_events": {
                "subject": self.params['nats']['graph_events_subject'],
                "callback": self.graph_event_callback,
            }
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
        #self.pipe_listener = PipeListener(self.params['asciinema']['rec_pipe'], cb=self.input_callback)
        #await self.pipe_listener.init()
        #self._loop.create_task(self.pipe_listener.loop())
        #print(f"Will send to: {self.params['nats']['subject_prefix']}.iodocument")

        #SurrealDb interface
        self.graphdb = SurrealDbInterface(self.params['surrealdb']['url'])
        await self.graphdb.init()
        self._loop.create_task(self.graphdb.loop())


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
        data = msg['data']
        #print(f"graph event received: {payload}")
#        if 'meta' in data.keys():
#            print("Meta:")
#            pprint(data['meta'])
#        else:
#            print(f"no Meta in: {data}")

        if 'payload' in data.keys():
            m = data['meta']
            p = data['payload']
            op = m['operation']
            ty = p['type']
            print(f"{op} {ty} ({p['id']})")
            if ty == "relationship":
                label = p['label']
                edge = {
                    "type": p['label'],
                    "A": {
                        "id": p['start']['id'],
                        "type": p['start']['labels'][0],
                    },
                    "B": {
                        "id": p['end']['id'],
                        "type": p['end']['labels'][0]
                    },
                }
                print(f"edge {op}: {edge}")
                await self.graphdb.update_edge(label, edge['A'], edge['B'])

            elif ty == "node":
                #print(f"New node to create: {p}")
                node = {
                    "id": p['id'],
                    "type": p['after']['labels'][0],
                }
                if node['type'] == "IoDocument":
                    node['props'] = {
                        "prompt": p['after']['properties']['ps1'],
                        "input": p['after']['properties']['user_input'],
                        "output": p['after']['properties']['output'],
                    }
                await self.graphdb.update_node(node)

                #print(f"node {op}: {node}")

            else:
                print(f"unknown payload type: {ty} ({op})")

#            pprint(data['payload'])

        else:
            #print(f"no Payload in: {data}")
            pass
    
    async def feedback_callback(self, msg):
        #print(f"feedback received: {msg}")
        pass
    
    async def iodoc_callback(self, msg):
        #print(f"iodoc received: {msg}")
        pass


async def app():
    mgr = Manager()
    await mgr.init()
    await mgr.run()

def main():
    asyncio.run(app())

if __name__ == "__main__":
    main()
