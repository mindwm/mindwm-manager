import asyncio
import hashlib
import json
import os
from base64 import b64encode
from enum import IntFlag
from signal import SIGINT, SIGTERM
from uuid import UUID, uuid4

from dbus_next.aio.message_bus import Message, MessageBus
from dbus_next.constants import BusType
from dbus_next.service import ServiceInterface, method
from decouple import config
from mindwm import logging
from mindwm.model.events import CloudEvent, IoDocumentEvent, TouchEvent
from mindwm.model.objects import Touch

from modules.nats_interface import NatsInterface
from modules.surrealdb_interface import SurrealDbInterface
from modules.tmux_session import TmuxSessionService

logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)
logger.debug("TEST DEBUG LEVEL")


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
                "url":
                config("MINDWM_NATS_URL",
                       default="nats://user:pass@127.0.0.1/"),
                "subject_prefix":
                config("MINDWM_NATS_SUBJECT_PREFIX",
                       default=f"org.mindwm.demouser.demohost"),
                "feedback_subject":
                config("MINDWM_NATS_FEEDBACK_SUBJECT",
                       default=
                       f"user-demouser.demohost-broker-kne-trigger._knative"),
                "listen": {},
            },
            "surrealdb": {
                "url":
                config("MINDWM_SURREALDB_URL",
                       default="ws://localhost:8000/mindwm/context_graph"),
                "enabled":
                config("MINDWM_SURREALDB_ENABLED", default=False, cast=bool),
            },
            "prompt_terminators":
            config("MINDWM_PROMPT_TERMINATORS", default="$,❯,➜").split(',')
        }
        self.params['nats']['listen'] = {
            "feedback": {
                "subject": f"{self.params['nats']['feedback_subject']}",
                # TODO: rename callback to `feedback`
                "callback": self.graph_event_callback,
            },
            # FIX: looks like we can't have two callbacks on the same subject
            #"actions": {
            #    "subject": f"{self.params['nats']['feedback_subject']}",
            #    "callback": self.action_callback,
            #},
        }

        self._loop = asyncio.get_event_loop()
        self.dbus_service = dbus_service
        self._bus = bus
        self._bus.export(f"{self.dbus_service['path']}service", self)
        self.nats = NatsInterface(self.params['nats']['url'])
        if self.params['surrealdb']['enabled']:
            self.graphdb = SurrealDbInterface(self.params['surrealdb']['url'])

        self.subscribers = {}

    async def _init(self):
        self.sessions = {}
        await self.nats._init()
        if self.params['surrealdb']['enabled']:
            await self.graphdb._init()
            self._loop.create_task(self.graphdb.loop())

        for k, v in self.params['nats']['listen'].items():
            await self.nats.subscribe(v['subject'], v['callback'])

    async def loop(self):
        await self._bus.wait_for_disconnect()

    async def notify(self, event: Event, payload: str):
        tmp = dict(self.subscribers)
        for k, v in tmp.items():
            if v & event:
                logger.debug(f"notify {k} about {event} with {payload}")
                res = await self.send2dbus(k, event, payload)
                if not res:
                    logger.error(
                        f"failed to send to {k}. Remove from subscribers")
                    del self.subscribers[k]

    async def send2dbus(self, destination, event, payload):
        dest = dict(list(map(lambda x: x.split('='), destination.split(','))))
        reply = [event, payload]
        try:
            msg = Message(destination=dest['destination'],
                          path=dest['path'],
                          interface=dest['interface'],
                          member=dest['member'],
                          signature='xs',
                          body=reply,
                          serial=self._bus.next_serial())
            reply = await self._bus.call(msg)
            #logger.debug(reply)
        except:
            return False

        return True
        #assert reply.message_type == MessageType.METHOD_RETURN

    async def iodoc_callback(self, uuid, iodoc):
        t = "iodocument"
        subject = self.sessions[uuid]['subject_iodoc']
        ev = IoDocumentEvent(data=iodoc)
        payload = CloudEvent(
            id=str(uuid4()),
            knativebrokerttl="255",
            specversion="1.0",
            type=t,
            source=f"{subject}",
            subject=iodoc.input,
            datacontenttype="application/json",
            data=ev,
        )

        logger.info(f"publush: {payload}")
        await self.nats.publish(subject, payload)

    async def action_callback(self, action):
        logger.debug(f"action received: {action}")
        #try:

        #action_type = action.data.type
        #logger.debug(f"action type: {action_type}")

    async def graph_event_callback(self, event):
        logger.debug(f"initial event: {event}")
        logger.debug(f"type: {type(event)}")
        if event['type'] == "showmessage":
            try:
                event['data'] = json.loads(event['data'])
                logger.debug(f"json loads: {event}")
                ev = CloudEvent.model_validate(event)
                show_message = ev.data
                logger.debug(f"show_message: {show_message}")
            except:
                logger.error("cannot cast to CloudEvent")

            with open('./.state/message.json', 'wt') as f:
                json.dump(show_message.data.model_dump(), f)

            cmd = f"display-popup -c/dev/pts/26 -E '/nix/store/yy52kw1fr7wfc1pzrk7p61yqrmxv89q2-python3-3.11.9-env/bin/python /home/pion/work/dev/mindwm/mindwm-manager/src/modules/tui/__init__.py'"
            logger.debug(f"send_cmd: {cmd}")
            logger.debug(f"sessions_keys: {self.sessions.keys()}")
            first_sess = list(self.sessions.keys())[0]
            await self.sessions[first_sess]['service'].send_cmd(cmd)
            return

        if not self.params['surrealdb']['enabled']:
            return

        if 'data' in event.keys():
            data = event['data']
        else:
            raise Exception("the data field in graph event is mandatory")

        source = event['source']
        operation = event['type']

        logger.debug(f"received {operation} for {source}")

        touch_nodes = []
        if source == 'graph.relationship':
            edge_from = event['data']['payload']['start']
            edge_to = event['data']['payload']['end']
            edge_name = event['data']['payload']['label']
            if operation == "created" or operation == "updated":
                node_from_id = edge_from['id']
                node_from_type = edge_from['labels'][0]
                node_to_id = edge_to['id']
                node_to_type = edge_to['labels'][0]

                node_from = await self.graphdb.get_node_by_id(
                    node_from_type, node_from_id)
                node_to = await self.graphdb.get_node_by_id(
                    node_to_type, node_to_id)
                if not node_from:
                    logger.debug(
                        f"Node: {node_from_type}:{node_from_id} not found")
                    touch_nodes.append(int(node_from_id))

                if not node_to:
                    logger.debug(
                        f"Node: {node_to_type}:{node_to_id} not found")
                    touch_nodes.append(int(node_to_id))

                await self.graphdb.update_edge(
                    edge_name,
                    {
                        "id": edge_from['id'],
                        "type": edge_from['labels'][0]
                    },
                    {
                        "id": edge_to['id'],
                        "type": edge_to['labels'][0]
                    },
                )
                event_payload = {
                    "node_type": "relationship",
                    "edge_name": edge_name,
                    "from": {
                        "id": edge_from['id'],
                        "type": edge_from['labels'][0]
                    },
                    "to": {
                        "id": edge_to['id'],
                        "type": edge_to['labels'][0]
                    },
                }
                await self.notify(Event.GRAPH_EDGE_CREATED,
                                  json.dumps(event_payload))
            else:
                logger.warning(
                    f"unimplemented opration {operation} for {source}")

        elif source == 'graph.node':
            node_id = event['data']['payload']['id']
            data = event['data']['payload']['after']
            if operation == "created" or operation == "updated":
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
                await self.notify(Event.GRAPH_NODE_CREATED,
                                  json.dumps(event_payload))
            else:
                logger.warning(
                    f"unimplemented opration {operation} for {source}")

        else:
            logger.error(f"Unknown source: {source}")

        if touch_nodes:
            payload = TouchEvent(id=str(uuid4()),
                                 knativebrokerttl="255",
                                 specversion="1.0",
                                 type="touch",
                                 source="mindwm.pion.snpnb.manager",
                                 subject="node",
                                 datacontenttype="application/json",
                                 data=Touch(ids=touch_nodes))

            logger.debug(f"NATS->{payload}")
            subject = f"{self.params['nats']['subject_prefix']}.touch"
            await self.nats.publish(subject, payload)
            #await asyncio.sleep(10)

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
        tmux_session_service = TmuxSessionService(
            session_uuid, dbus_service, tmux_session,
            self.params['prompt_terminators'], self._bus, self.iodoc_callback)

        await tmux_session_service._init()

        self.sessions[session_uuid] = {
            "service":
            tmux_session_service,
            "subject_iodoc":
            f"{self.params['nats']['subject_prefix']}.tmux.{b64socket}.{session_uuid}.{session_id}.{pane_id}.iodocument",
            "subject_feedback":
            f"{self.params['nats']['subject_prefix']}.tmux.{b64socket}.{session_uuid}.{session_id}.{pane_id}.feedback",
        }
        self.tmux_control = self._loop.create_task(tmux_session_service.loop())
        logger.debug(str(self.sessions))
        return True

    #@method(sender_keyword="sender")
    @method()
    async def subscribe(self, events: 'x', subscriber: 's') -> 'b':
        logger.info(f"{subscriber} subscribed on {events}")
        self.subscribers[subscriber] = events
        logger.info(self.subscribers)
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

        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()

        await self._bus.request_name(self.dbus_service['destination'])
        logger.info(f"DBus service: {self.dbus_service}")

        self.service = ManagerService(self.dbus_service, self._bus)
        await self.service._init()

    async def do_cleanup(self):
        logger.info("cleaning up")

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
