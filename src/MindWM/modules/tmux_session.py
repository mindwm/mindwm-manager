import logging
import asyncio
from MindWM.modules.subprocess import Subprocess
from dbus_next.service import ServiceInterface, method, signal, dbus_property
from dbus_next.aio.message_bus import Message, MessageType, MessageBus
from dbus_next.constants import BusType
from MindWM.modules.pipe_listener import PipeListener


logger = logging.getLogger(__name__)

class TmuxSessionService(ServiceInterface):
    def __init__(self, uuid, dbus_service, tmux_session, prompt_terminators, bus, iodoc_callback):
        super().__init__(dbus_service['destination'])
        self._loop = asyncio.get_event_loop()
        self.dbus_service = dbus_service
        self.tmux_session = tmux_session
        self.prompt_terminators = prompt_terminators
        self._iodoc_callback = iodoc_callback
        self._bus = bus
        self.uuid = uuid
        self._bus.export(f"{self.dbus_service['path']}tmux_session/{uuid.replace('-','_')}", self)

    async def _init(self):
        logger.debug(f"spawning tmux conttrol for {self.tmux_session}")
        self.subprocess = Subprocess(
            f"tmux -S{self.tmux_session['socket']} -C a -t%{self.tmux_session['pane_id']}",
            "^(?!%output.*)",
            self.output_callback,
            self.uuid,
            self.terminated_callback
            )
        self._subproc_running = False
        self.tmux_control = self._loop.create_task(self.subprocess.start())
        logger.info(f"creating new PipeListener for {self.tmux_session}")
        self.pipe_path = f"/tmp/mindwm-asciinema-{self.uuid}.socket"
        self.pipe_listener = PipeListener(
            self.pipe_path,
            self.prompt_terminators,
            self.pipe_callback
        )
        await self.pipe_listener._init()
        self._loop.create_task(self.pipe_listener.loop())
        logger.debug(f"starting asciinema via tmux control for {self.uuid}")
        asciinema_rec_cmd = f"asciinema rec --stdin --append {self.pipe_path}"
        tmux_cmd = f"send-keys -t%{self.tmux_session['pane_id']} '{asciinema_rec_cmd}' Enter"
        logger.debug(f"starting asciinema with: {tmux_cmd}")
        while not self._subproc_running:
            await asyncio.sleep(0.1)

        await self.subprocess.send_stdio(tmux_cmd)
        logger.debug("need to watch for asciinema exit and shotdown the PipeListener and self")
        return self.uuid

    async def output_callback(self, uid, output, is_terminated):
        self._subproc_running = not is_terminated
        #logger.debug(f"{uid}: {output} ({is_terminated})")

    async def terminated_callback(self, uid):
        logger.debug(f"{uid}: terminated")

    async def pipe_callback(self, payload):
        await self._iodoc_callback(self.uuid, payload)

    async def loop(self):
        logger.debug(f"{self.tmux_control}")
        await self._bus.wait_for_disconnect()
