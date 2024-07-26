import asyncio
from base64 import b64encode
from dbus_next.service import ServiceInterface, method, signal, dbus_property
from dbus_next.aio.message_bus import Message, MessageType, MessageBus
from dbus_next.constants import BusType

from decouple import config
from enum import IntFlag, auto
import hashlib
import json
from pprint import pprint
from signal import SIGINT, SIGTERM
from uuid import UUID, uuid4

from MindWM.modules.nats_interface import NatsInterface
from MindWM.modules.subprocess import Subprocess
from MindWM.modules.surrealdb_interface import SurrealDbInterface
from MindWM.modules.tmux_session import TmuxSessionService
from MindWM.models import IoDocumentEvent

class Event(IntFlag):
    GRAPH_NODE_CREATED = 1
    GRAPH_NODE_DELETED = 2
    GRAPH_EDGE_CREATED = 4
    GRAPH_EDGE_DELETED = 8


class ManagerService(ServiceInterface):
    def __init__(self, dbus_service, bus):
        super().__init__(dbus_service['destination'])
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
            "prompt_terminators": config("MINDWM_PROMPT_TERMINATORS", default="$,❯,➜").split(',')
        }
        self.params['nats']['listen'] = {
            "graph_events": {
                "subject": self.params['nats']['graph_events_subject'],
                "callback": self.graph_event_callback,
            }
        }
        self._loop = asyncio.get_event_loop()
        self.dbus_service = dbus_service
        self._bus = bus
        self._bus.export(f"{self.dbus_service['path']}service", self)
        self.nats = NatsInterface(self.params['nats']['url'])
        self.graphdb = SurrealDbInterface(self.params['surrealdb']['url'])
        self.subscribers = {}

    async def _init(self):
        self.sessions = {}
        await self.nats._init()
        await self.graphdb._init()
        self._loop.create_task(self.graphdb.loop())

        for k, v in self.params['nats']['listen'].items():
            await self.nats.subscribe(v['subject'], v['callback'])

    async def loop(self):
        await self._bus.wait_for_disconnect()

    async def notify(self, event : Event, payload : str):
        tmp = dict(self.subscribers)
        for k, v in tmp.items():
            if v & event:
                print(f"notify {k} about {event} with {payload}")
                res = await self.send2dbus(k, event, payload)
                if not res:
                    print(f"failed to send to {k}. Remove from subscribers")
                    del self.subscribers[k]

    async def send2dbus(self, destination, event, payload):
        dest = dict(list(map(lambda x: x.split('='), destination.split(','))))
        reply = [event, payload]
        try:
            msg = Message(
                destination=dest['destination'],
                path=dest['path'],
                interface=dest['interface'],
                member=dest['member'],
                signature='xs',
                body=reply,
                serial=self._bus.next_serial()
            )
            reply = await self._bus.call(msg)
            print(reply)
        except:
            return False

        return True
        #assert reply.message_type == MessageType.METHOD_RETURN


    async def iodoc_callback(self, uuid, iodoc):
        t = "iodocument"
        subject = self.sessions[uuid]['subject_iodoc']
        payload = IoDocumentEvent(
            id = str(uuid4()),
            knativebrokerttl = "255",
            specversion = "1.0",
            type = t,
            source = f"{subject}",
            subject = f"{subject}",
            datacontenttype = "application/json",
            data = iodoc
            )

        print(f"NATS->{subject}\n{payload}")
        await self.nats.publish(subject, bytes(payload.to_json(), encoding='utf-8'))

    async def graph_event_callback(self, event):
        #pprint(event)
        if 'data' in event.keys():
            data = event['data']
        else:
            raise Exception("the data field in graph event is mandatory")

        source = event['source']
        operation = event['type']

        print(f"received {operation} for {source}")

        if source == 'graph.relationship':
            edge_from = event['data']['payload']['start']
            edge_to = event['data']['payload']['end']
            edge_name = event['data']['payload']['label']
            if operation == "created":
                await self.graphdb.update_edge(
                    edge_name,
                    {"id": edge_from['id'], "type": edge_from['labels'][0]},
                    {"id": edge_to['id'], "type": edge_to['labels'][0]},
                )
                event_payload = {
                    "node_type": "relationship",
                    "edge_name": edge_name,
                    "from": {"id": edge_from['id'], "type": edge_from['labels'][0]},
                    "to": {"id": edge_to['id'], "type": edge_to['labels'][0]},
                }
                await self.notify(Event.GRAPH_EDGE_CREATED, json.dumps(event_payload))
            else:
                print(f"unimplemented opration {operation} for {source}")

        elif source == 'graph.node':
            node_id = event['data']['payload']['id']
            data = event['data']['payload']['after']
            if operation == "created":
                await self.graphdb.update_node({
                    "id": node_id,
                    "type": data['labels'][0],
                    "payload": data
                })
                event_payload = {
                    "node_id": node_id,
                    "node_type": data['labels'][0],
                    "node_data": data,
                }
                await self.notify(Event.GRAPH_NODE_CREATED, json.dumps(event_payload))
            else:
                print(f"unimplemented opration {operation} for {source}")

        else:
            print(f"Unknown source: {source}")


    @method()
    async def tmux_join(self, tmux_string: 's') -> 'b':
        [socket_path, pid, session_id, pane] = tmux_string.split(',')
        dbus_service = self.dbus_service
        pane_id = pane[1:]
        tmux_session = {
            "socket": socket_path,
            "session_id": session_id,
            "pane_id": pane_id,
        }
        b64socket = b64encode(socket_path.encode('utf-8')).decode('utf-8')
        session_string = f"{self.params['nats']['subject_prefix']}.tmux.{b64socket}.{session_id}.{pane_id}"
        hex_string = hashlib.md5(session_string.encode('utf-8')).hexdigest()
        session_uuid = str(UUID(hex=hex_string))
        tmux_session_service = TmuxSessionService(session_uuid, dbus_service, tmux_session, self.params['prompt_terminators'], self._bus, self.iodoc_callback)

        await tmux_session_service._init()

        self.sessions[session_uuid] = {
            "service": tmux_session_service,
            "subject_iodoc": f"{self.params['nats']['subject_prefix']}.tmux.{b64socket}.{session_uuid}.{session_id}.{pane_id}.iodocument",
            "subject_feedback": f"{self.params['nats']['subject_prefix']}.tmux.{b64socket}.{session_uuid}.{session_id}.{pane_id}.feedback",
        }
        self.tmux_control = self._loop.create_task(tmux_session_service.loop())
        pprint(self.sessions)
        return True

    #@method(sender_keyword="sender")
    @method()
    async def subscribe(self, events : 'x', subscriber: 's') -> 'b':
        print(f"{subscriber} subscribed on {events}")
        self.subscribers[subscriber] = events
        print(self.subscribers)
        return True

class Manager:
    def _init__(self):
        pass

    async def _init(self):
        self.dbus_service = {
            "destination": "org.mindwm.client.manager",
            "path": "/",
            "interface": "org.mindwm.client.manager"
        }

        self._bus = await MessageBus(bus_type = BusType.SESSION).connect()

        await self._bus.request_name(self.dbus_service['destination'])
        print(f"DBus service: {self.dbus_service}")

        self.service = ManagerService(self.dbus_service, self._bus)
        await self.service._init()

    async def do_cleanup(self):
        print("cleaning up")
        pass

    async def loop(self):
        try:
            await self._bus.wait_for_disconnect()
        except:
            await self.do_cleanup()

    async def show(self):
        await self.service.show()

async def run():
    mgr = Manager()
    await mgr._init()
    await mgr.loop()

def main():
    loop = asyncio.get_event_loop()
    main_task = asyncio.ensure_future(run())
    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, main_task.cancel)
    try:
        loop.run_until_complete(main_task)
    finally:
        loop.close()

if __name__ == "__main__":
    main()
