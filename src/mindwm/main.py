import asyncio
from base64 import b64encode
from dbus_next.service import ServiceInterface, method, signal, dbus_property
from dbus_next.aio.message_bus import Message, MessageType, MessageBus
from dbus_next.constants import BusType
from decouple import config
import hashlib
import json
from pprint import pprint
from signal import SIGINT, SIGTERM
from uuid import UUID, uuid4

from mindwm.modules.nats_interface import NatsInterface
from mindwm.modules.pipe_listener import PipeListener
from mindwm.modules.subprocess import Subprocess
from mindwm.modules.surrealdb_interface import SurrealDbInterface


class TmuxSessionService(ServiceInterface):
    def __init__(self, uuid, dbus_service, tmux_session, bus, iodoc_callback):
        super().__init__(dbus_service['destination'])
        self._loop = asyncio.get_event_loop()
        self.dbus_service = dbus_service
        self.tmux_session = tmux_session
        self._iodoc_callback = iodoc_callback
        self._bus = bus
        self.uuid = uuid
        self._bus.export(f"{self.dbus_service['path']}tmux_session/{uuid.replace('-','_')}", self)

    async def _init(self):
        print(f"spawning tmux conttrol for {self.tmux_session}")
        self.subprocess = Subprocess(
            f"tmux -S{self.tmux_session['socket']} -C a -t%{self.tmux_session['pane_id']}",
            "^(?!%output.*)",
            self.output_callback,
            self.uuid,
            self.terminated_callback
            )
        self._subproc_running = False
        self.tmux_control = self._loop.create_task(self.subprocess.start())
        print(f"creating new PipeListener for {self.tmux_session}")
        self.pipe_path = f"/tmp/mindwm-asciinema-{self.uuid}.socket"
        self.pipe_listener = PipeListener(
            self.pipe_path,
            self.pipe_callback
        )
        await self.pipe_listener._init()
        self._loop.create_task(self.pipe_listener.loop())
        print(f"starting asciinema via tmux control for {self.uuid}")
        asciinema_rec_cmd = f"asciinema rec --stdin --append {self.pipe_path}"
        tmux_cmd = f"send-keys -t%{self.tmux_session['pane_id']} '{asciinema_rec_cmd}' Enter"
        print(f"starting asciinema with: {tmux_cmd}")
        while not self._subproc_running:
            await asyncio.sleep(0.1)

        await self.subprocess.send_stdio(tmux_cmd)
        print("need to watch for asciinema exit and shotdown the PipeListener and self")
        return self.uuid

    async def output_callback(self, uid, output, is_terminated):
        self._subproc_running = not is_terminated
        print(f"{uid}: {output} ({is_terminated})")

    async def terminated_callback(self, uid):
        print(f"{uid}: terminated")

    async def pipe_callback(self, payload):
        await self._iodoc_callback(self.uuid, payload)

    async def loop(self):
        print(f"{self.tmux_control}")
        await self._bus.wait_for_disconnect()


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

    async def _init(self):
        self.sessions = {}
        await self.nats._init()
        await self.graphdb._init()
        self._loop.create_task(self.graphdb.loop())

        for k, v in self.params['nats']['listen'].items():
            await self.nats.subscribe(v['subject'], v['callback'])

    async def loop(self):
        await self._bus.wait_for_disconnect()

    async def iodoc_callback(self, uuid, iodoc):
        print(f"{uuid}: payload: {iodoc}")
        t = "iodocument"
        subject = self.sessions[uuid]['subject_iodoc']
        payload = {
            "knativebrokerttl": "255",
            "specversion": "1.0",
            "type": t,
            "source": f"{subject}",
            "subject": f"{subject}",
            "datacontenttype": "application/json",
            "data": {
               t: iodoc,
            },
            "id": str(uuid4()),
        }

        print(f"sent to subj: {subject}: {payload}")
        await self.nats.publish(subject, bytes(json.dumps(payload), encoding='utf-8'))

    async def graph_event_callback(self, event):
        pprint(event)

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
        tmux_session_service = TmuxSessionService(session_uuid, dbus_service, tmux_session, self._bus, self.iodoc_callback)

        await tmux_session_service._init()

        self.sessions[session_uuid] = {
            "service": tmux_session_service,
            "subject_iodoc": f"{self.params['nats']['subject_prefix']}.tmux.{b64socket}.{session_uuid}.{session_id}.{pane_id}.iodocument",
            "subject_feedback": f"{self.params['nats']['subject_prefix']}.tmux.{b64socket}.{session_uuid}.{session_id}.{pane_id}.feedback",
        }
        self.tmux_control = self._loop.create_task(tmux_session_service.loop())
        pprint(self.sessions)
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

async def main():
    mgr = Manager()
    await mgr._init()
    await mgr.loop()

loop = asyncio.get_event_loop()
main_task = asyncio.ensure_future(main())
for signal in [SIGINT, SIGTERM]:
    loop.add_signal_handler(signal, main_task.cancel)
try:
    loop.run_until_complete(main_task)
finally:
    loop.close()
