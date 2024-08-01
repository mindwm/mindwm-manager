import logging
import asyncio
from surrealdb import AsyncSurrealDB

logger = logging.getLogger(__name__)

class SurrealDbInterface:
    def __init__(self, url):
        self._url = url
        self._db = AsyncSurrealDB(self._url)

    async def _init(self):
        await self._db.connect()
        logger.info(f"Connected to SurrealDB on {self._url}")

    async def loop(self):
        logger.info(f"Starting main loop of SurrealDB Interface")
        while True:
            await asyncio.sleep(1)

    async def update_node(self, node):
        q = f"""
            update {node['type']}:{node['id']} content {{ {node['payload']} }};
        """
        await self._db.query(q)

    async def update_edge(self, edge_type, node_a, node_b):
        await self._db.query(f"""
          relate {node_a['type']}:{node_a['id']}->{edge_type}->{node_b['type']}:{node_b['id']}
        """
        )

    async def get_node_by_id(self, node_type, node_id):
        q = f"""
            SELECT * from {node_type} where id = {node_type}:{node_id};
        """
        #logger.debug(f"Query: {q}")
        res = await self._db.query(q)
        return res
