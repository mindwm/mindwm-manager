import asyncio
import io
import os
import sys
from tabulate import tabulate
import textfsm
import json

class TextProcessor:
    templates = {
        "ifconfig": "unix_ifconfig"
    }
    def __init__(self):
        pass

    async def init(self):
        pass

    def table2json(self, a):
        return json.dumps(
            list(map(lambda x: {x[0][1]: dict(x[1:])}, map(lambda x: list(zip(a[1], x)), a[0])))
        )
        #json.dumps(list(map(lambda x: {x[1]: dict(x[1:])}, map(lambda x: list(zip(header, x)), table))))

    async def parse(self, cmd, output):
        #print(f"parsing output of '{cmd}'")
        try:
            template = self.templates[cmd]
        except KeyError:
            raise NotImplementedError(f"{cmd} is not supported yet")

        #path = os.path.dirname(sys.modules[__name__].__file__)
        #print(output)
        path = os.path.dirname(sys.modules[self.__class__.__module__].__file__)
        with open(f"data/templates/{template}.textfsm", "r") as f:
            parser = textfsm.TextFSM(io.StringIO(f.read()))
            header = parser.header
            #return tabulate(parser.ParseText(output), headers=header)
            return self.table2json((parser.ParseText(output), header))
            #return [parser.ParseText(output), header]
