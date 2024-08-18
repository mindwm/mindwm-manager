import asyncio
import functools
import re

from mindwm import logging

logger = logging.getLogger(__name__)


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
        protocol_factory = functools.partial(MyProtocol,
                                             self._reader,
                                             limit=2**16,
                                             loop=self._loop)

        transport, protocol = await self._loop.subprocess_exec(
            protocol_factory,
            *self._cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

        proc = asyncio.subprocess.Process(transport, protocol, self._loop)
        self._proc = proc
        (out, err), _ = await asyncio.gather(proc.communicate(),
                                             self.callback_on_output())
        await self._terminate_callback(self._uid)

    async def callback_on_output(self):
        async for line in self._reader:
            if self._output_regex:
                out_string = line.decode('utf-8')
                if self._output_regex.match(out_string):
                    await self._callback(self._uid, line, False)
            else:
                await self._callback(self._uid, line, False)

    async def terminate(self):
        if self._proc:
            await self._proc.terminate()

    async def send_stdio(self, string):
        if self._proc:
            s = string + '\n'
            logger.debug(f"send to stdio: {s}")
            self._proc.stdin.write(s.encode())
        else:
            logger.debug(f"{self._uid} is terminated")
