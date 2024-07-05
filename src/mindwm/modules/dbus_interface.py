#!/usr/bin/env python3
import re
import sys
import os
import functools
from uuid import uuid4

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

from dbus_next.service import ServiceInterface, method, signal, dbus_property
from dbus_next.aio.message_bus import Message, MessageType, MessageBus
from dbus_next.constants import BusType
from dbus_next import Variant

import asyncio
from pprint import pprint
from uuid import uuid4
from base64 import b64encode

# credits to https://blog.dalibo.com/2022/09/12/monitoring-python-subprocesses.html
class MyProtocol(asyncio.subprocess.SubprocessStreamProtocol):
    def __init__(self, reader, limit, loop):
        super().__init__(limit=limit, loop=loop)
        self._reader = reader

    def pipe_data_received(self, fd, data):
        """Called when the child process writes data into its stdout
        or stderr pipe.
        """
        super().pipe_data_received(fd, data)
        if fd == 1:
            self._reader.feed_data(data)

        if fd == 2:
            self._reader.feed_data(data)

    def pipe_connection_lost(self, fd, exc):
        """Called when one of the pipes communicating with the child
        process is closed.
        """
        super().pipe_connection_lost(fd, exc)
        if fd == 1:
            if exc:
                self._reader.set_exception(exc)
            else:
                self._reader.feed_eof()

        if fd == 2:
            if exc:
                self._reader.set_exception(exc)
            else:
                self._reader.feed_eof()

class Subprocess():
    def __init__(self, cmd, output_regex, callback, uid, terminate_callback):
        self._loop = asyncio.get_event_loop()
        self._cmd = cmd.split()
        try:
            if output_regex != "":
                self._output_regex = re.compile(output_regex)
            else:
                self._output_regex = None
        except Exception as e:
            self._output_regex = None

        self._callback = callback
        self._uid = uid
        self._proc = None
        self._terminate_callback = terminate_callback

    async def start(self):
        self._reader = asyncio.StreamReader(loop=self._loop)
        protocol_factory = functools.partial(
            MyProtocol, self._reader, limit=2**16, loop=self._loop
        )

        transport, protocol = await self._loop.subprocess_exec(
            protocol_factory,
            *self._cmd,
            stdin = asyncio.subprocess.PIPE,
            stdout = asyncio.subprocess.PIPE,
            stderr = asyncio.subprocess.PIPE)

        proc = asyncio.subprocess.Process(transport, protocol, self._loop)
        self._proc = proc
        (out, err), _ = await asyncio.gather(proc.communicate(), self.callback_on_output())
        await self._terminate_callback(self._uid)

    async def callback_on_output(self):
        async for line in self._reader:
            if self._output_regex:
                out_string = line.decode('utf-8')
                if self._output_regex.match(out_string):
                    await self._callback(self._uid, line, 'stdout')
            else:
                await self._callback(self._uid, line, 'stdout')

    async def terminate(self):
        if self._proc:
            await self._proc.terminate()

    async def send_stdio(self, string):
        if self._proc:
            s = string + '\n'
            print(f"send to stdio: {s}")
            self._proc.stdin.write(s.encode())


class SpawnedCommand():
    def __init__(self, cmd, output_regex, uid, subprocess, dest):
        self._cmd = cmd
        self._output_regex = output_regex
        self._uid = uid
        self._subp = subprocess
        self.dest = dict(list(map(lambda x: x.split('='), dest.split(','))))


class ManagerInterface(ServiceInterface):
    def __init__(self, name, bus):
        super().__init__(name)
        self._string_prop = 'kevin'
        self._spawned_commands = []
        self._loop = asyncio.get_event_loop()
        self._bus = bus

    def findByUid(self, uid):
        for p in self._spawned_commands:
            if p._uid == uid:
                return p

        return None

    async def subp_terminate_callback(self, uid):
        p = self.findByUid(uid)
        if p:
            await self.callback_output(uid, b"", "", True)
            self._spawned_commands.remove(p)


    async def callback_output(self, uid, output, label, terminated = False):
        p = self.findByUid(uid)
        if not p:
            raise Exception(f"process not found {uid}")

        reply = [uid, output.decode("utf-8").strip(), terminated]
        msg = Message(
            destination=p.dest['destination'],
            path=p.dest['path'],
            interface=p.dest['interface'],
            member=p.dest['member'],
            signature='ssb',
            body=reply,
            serial=self._bus.next_serial()
        )
        reply = await self._bus.call(msg)
        assert reply.message_type == MessageType.METHOD_RETURN

    @method()
    async def Run(self, cmd: 's', output_regex: 's', output_to: 's') -> 's':
        uid = str(uuid4())
        subp = Subprocess(
                cmd,
                output_regex,
                self.callback_output,
                uid,
                self.subp_terminate_callback)
        self._spawned_commands.append(
                SpawnedCommand(
                    cmd, output_regex, uid, subp, output_to))
        #await self._subp.start()
        self._loop.create_task(subp.start())
        print(f"echo: ({uid}) {cmd}")
        return uid

    @method()
    async def KillAll(self):
        for p in self._spawned_commands:
            await p._subp.terminate()

        self._spawned_commands.clear()

    @method()
    async def Kill(self, uid: 's'):
        p = self.findByUid(uid)
        if p:
            await p._subp.terminate()
            self._spawned_commands.remove(p)

    @method()
    async def ListSpawned(self) -> 'a(ss)':
        res = []
        for p in self._spawned_commands:
            res.append([p._uid, p._cmd])

        return res

    @method()
    async def SendStdin(self, uid: 's', string: 's'):
        p = self.findByUid(uid)
        if p:
            await p._subp.send_stdio(string)

    @method()
    def Echo(self, what: 's') -> 's':
        print(f"echo: {what}")
        return what

    @method()
    def EchoMultiple(self, what1: 's', what2: 's') -> 'ss':
        return [what1, what2]

    @method()
    def GetVariantDict(self) -> 'a{sv}':
        return {
            'foo': Variant('s', 'bar'),
            'bat': Variant('x', -55),
            'a_list': Variant('as', ['hello', 'world'])
        }

    @dbus_property(name='StringProp')
    def string_prop(self) -> 's':
        return self._string_prop

    @string_prop.setter
    def string_prop_setter(self, val: 's'):
        self._string_prop = val

    @signal()
    def feedback_message(self, msg: 's') -> 's':
        return msg

    @signal()
    def signal_multiple(self) -> 'ss':
        return ['hello', 'world']


class Actions(ServiceInterface):
    def __init__(self, name, bus, dest, path, interface):
        super().__init__(name)
        self._bus = bus
        self._destination = dest
        self._path = path
        self._interface = interface
        self._connected = False

    @method()
    async def join(self, tmux_string : 's') -> 'i':
        '''
            pass $TMUX,$TMUX_PANE as a tmux_string
        '''
        [socket_path, pid, session_id, pane] = tmux_string.split(',')
        self._tmux_socket = socket_path
        self._tmux_pid = pid
        self._tmux_session = session_id
        self._tmux_pane_id = pane[1:]
        # attach to tmux socket in control mode
        destination = "org.mindwm.client.manager"
        path = "/"
        interface = "org.mindwm.client.manager"
        member = "Run"
        signature = "sss"
        callback_member = "join_output"

        body = [
            f"tmux -S{self._tmux_socket} -C a -t%{self._tmux_pane_id}",
            f"^(?!%output.*)",
            f"destination={self._destination},path={self._path},interface={self._interface},member={callback_member}"
        ]

        msg = Message(
            destination=destination,
            path=path,
            interface=interface,
            member=member,
            signature=signature,
            body=body,
            serial=self._bus.next_serial()
        )
        reply = await self._bus.call(msg)
        assert reply.message_type == MessageType.METHOD_RETURN
        self._tmux_process_uid = reply.body[0]
        # TODO: better to return from this method and continue inside a worker thread
        while not self._connected:
            await asyncio.sleep(0.1)

        session_uid = uuid4()
        session_subject = f"mindwm.pion.snpnb.{b64encode(self._tmux_socket.encode('utf-8')).decode('utf-8')}.{uuid4()}.{self._tmux_session}.{self._tmux_pane_id}"
        asciinema_socket = f"/tmp/asciinema-{session_subject}.socket"
        join_cmd = f"asciinema rec --stdin --append {asciinema_socket}"
        msg.body = [self._tmux_process_uid, f'send-keys -t %{self._tmux_pane_id} "{join_cmd}" Enter']
        msg.member = "SendStdin"
        msg.signature = 'ss'
        reply = await self._bus.call(msg)
        assert reply.message_type == MessageType.METHOD_RETURN

        # terminate watcher
        msg.body = [self._tmux_process_uid]
        msg.member = "Kill"
        msg.signature = 's'
        await self._bus.call(msg)

        return 0

    @method()
    async def join_output(self, uid: 's', output: 's', is_terminated: 'b') -> 'i':
        if not is_terminated:
            self._connected = True
        else:
            self._connected = False

        print(f"({uid}) {output} ({is_terminated})")
        return 0

class DbusInterface():
    def __init__(self):
        pass

    async def init(self):
        self.name = 'org.mindwm.client.manager'
        self.path = '/'
        self.interface_name = 'org.mindwm.client.manager'
    
        bus = await MessageBus(bus_type = BusType.SESSION).connect()
        self.interface = ManagerInterface(self.interface_name, bus)
        self.actions_interface = Actions(self.interface_name, bus, self.name, "/actions", self.interface_name)
        bus.export(self.path, self.interface)
        #bus.export(f"/{self.interface_name.replace('.','/')}/actions", self.actions_interface)
        bus.export(f"/actions", self.actions_interface)

        await bus.request_name(self.name)
        print(f'service up on name: "{self.name}", path: "{self.path}", interface: "{self.interface_name}"')
        await bus.wait_for_disconnect()

    async def feedback_message(self, msg):
        if self.interface:
            self.interface.feedback_message(msg)

if __name__ == "__main__":
    obj = DbusInterface()
    asyncio.get_event_loop().run_until_complete(obj.init())
