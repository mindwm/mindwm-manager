import asyncio
from surrealdb import AsyncSurrealDB

class SurrealDbInterface:
    def __init__(self, url):
        self._url = url
        self._db = AsyncSurrealDB(self._url)

    async def _init(self):
        await self._db.connect()
        print(f"Connected to SurrealDB on {self._url}")

    async def loop(self):
        print(f"Starting main loop of SurrealDB Interface")
        while True:
            await asyncio.sleep(1)

    async def update_node(self, node):
        await self._db.create(f"{node['type']}:{node['id']}", node['payload'])

    async def update_edge(self, edge_type, node_a, node_b):
        await self._db.query(f"""
          relate {node_a['type']}:{node_a['id']}->{edge_type}->{node_b['type']}:{node_b['id']}
        """
        )
