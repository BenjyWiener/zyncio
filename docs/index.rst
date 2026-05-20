======
|logo|
======

.. |logo| image:: _static/ZyncIO.png
    :alt: ZyncIO logo

.. rst-class:: lead

    Write dual sync/async interfaces with minimal duplication.

|licence| |version| |pyversions|

.. |licence| image:: https://img.shields.io/badge/license-MIT-green

.. |version| image:: https://img.shields.io/pypi/v/zyncio.svg
    :target: https://pypi.python.org/pypi/zyncio

.. |pyversions| image:: https://img.shields.io/pypi/pyversions/zyncio.svg
    :target: https://pypi.python.org/pypi/zyncio

..

    If I had a nickel for every variation of my library that I maintain, I'd have two nickels... which isn't a lot, but
    it's weird that I had to write everything twice.

    -- Dr. Doofenshmirtz, before discovering ZyncIO.

ZyncIO is a small library with a simple goal: make it easy to write libraries that support both sync and async usage,
*without* writing everything twice.

.. code-block:: python
    :caption: Example

    class BaseClient:
        def __init__(self, sock: socket.socket) -> None:
            self.sock: socket.socket = sock

        @zyncio.zmethod
        async def send_msg(self, data: bytes) -> None:
            if zyncio.is_sync(self):
                self.sock.sendall(data)
            else:
                loop = asyncio.get_running_loop()
                await loop.sock_sendall(self.sock, data)

        @zyncio.zmethod
        async def recv_msg(self, n: int) -> bytes:
            buf = b''
            if zyncio.is_sync(self):
                while len(buf) < n:
                    buf += self.sock.recv(n)
            else:
                loop = asyncio.get_running_loop()
                while len(buf) < n:
                    buf += await loop.sock_recv(self.sock, n)
            return buf

        @zyncio.zmethod
        async def do_handshake(self) -> None:
            # `.z` (or `.call_zync`) on bound `zmethod`'s (and similar callables)
            # always returns a coroutine, so you can `await` it regardless of the
            # running mode.
            await self.send_msg.z(HANDSHAKE_REQ)
            response = await self.recv_msg.z(len(HANDSHAKE_RESP))
            if response != HANDSHAKE_RESP:
                raise RuntimeError('Handshake failed')

        @zyncio.zproperty
        async def status(self) -> str:
            await self.send_msg.z(STATUS_REQ)
            return (await self.recv_msg.z(STATUS_RESP_LEN)).decode()


    class SyncClient(BaseClient, zyncio.SyncMixin):
        pass


    class AsyncClient(BaseClient, zyncio.AsyncMixin):
        def __init__(self, sock: socket.socket) -> None:
            super().__init__(sock)
            self.sock.setblocking(False)


    sync_client = SyncClient(sock)
    sync_client.do_handshake()  # Magically sync!
    print('Status:', sync_client.status)  # Sync property


    async def use_async_client():
        async_client = AsyncClient(sock)
        await async_client.do_handshake()  # Magically async!
        print('Status:', await sync_client.status())  # Async func

    asyncio.run(use_async_client())

Ready to get started? Check out :doc:`the tutorial <tutorial/index>`, or dive into the :doc:`api/index`.

.. toctree::
    :maxdepth: 2
    :hidden:

    tutorial/index
    why-zyncio
    api/index
