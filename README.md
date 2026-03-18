# ZyncIO

Write dual sync/async interfaces with minimal duplication.

[![PyPI - Version](https://img.shields.io/pypi/v/zyncio.svg)](https://pypi.org/project/zyncio)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/zyncio.svg)](https://pypi.org/project/zyncio)
[![Coverage](https://coverage-badge.samuelcolvin.workers.dev/benjywiener/zyncio.svg)](https://coverage-badge.samuelcolvin.workers.dev/redirect/benjywiener/zyncio)

---

## What is ZyncIO?

> If I had a nickel for every almost identical interface I had to write,
> I'd have two nickels... which isn't a lot, but it's weird that I had to
> write it twice.
>
> – Dr. Doofenshmirtz, before discovering ZyncIO.

ZyncIO allows you to write interfaces that can be used synchronously and asynchronously,
while avoiding the code duplication this usually entails.

## How does it work?

ZyncIO works due to the fact that in Python you can actually run a coroutine **without an event loop**,
as long as your chain of `await`s consists exclusively of other coroutines (i.e. no `Future`s or `Task`s):

> The behavior of `await coroutine` is effectively the same as invoking a regular, synchronous Python function.
>
> – [A Conceptual Overview of `asyncio`](https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html#await)

To run such a coroutine, we simply call `send(None)`, catch the `StopIteration`, and extract its `value`:

```python
coro = pure_coroutine_func()
try:
    coro.send(None)
except StopIteration as e:
    ret = e.value
```

This means that a single `async def` function can be made to run in both synchronous and asynchronous
contexts, as long as we have a way to determine which mode we're currently using:

```python
async def zync_sleep(zync_mode: zyncio.Mode, secs: float) -> None:
    if zync_mode is zyncio.SYNC:
        time.sleep(secs)
    else:
        await asyncio.sleep(secs)
```

But this isn't very convenient; you need to pass an additional parameter, and running in
sync mode is pretty clunky. That's where `zyncio.zfunc` comes in:

```python
@zyncio.zfunc
async def zync_sleep(zync_mode: zyncio.Mode, secs: float) -> None:
    ...

zync_sleep.run_sync(3)
asyncio.run(zync_sleep.run_async(3))

@zyncio.zfunc
async def sleep_3(zync_mode: zyncio.Mode) -> None:
    await zync_sleep.run_zync(zync_mode, 3)
    # or
    await zync_sleep[zync_mode](3)
```

### The real magic: `SyncMixin`/`AsyncMixin`, `zyncio.zmethod`, and `zyncio.zproperty`

The real power of ZyncIO comes out when implementing client interfaces:

1. Implement a single base client, using the `zyncio.zmethod` and `zyncio.zproperty`
   decorators.

2. Create two subclasses a sync client and an async client, adding the `zyncio.SyncMixin`
   and `zyncio.AsyncMixin` mixins respectively.

3. All of your `zyncio.zmethod`s magically become sync methods on the sync client and async
   methods on the async client.

   All of the `zyncio.zproperty`s magically become properties on the sync client, and async
   methods on the async client.

```python
class BaseClient(zyncio.ZyncBase):
    def __init__(self, sock: socket.socket) -> None:
        self.sock: socket.socket = sock

    @zyncio.zmethod
    async def send_msg(self, data: bytes) -> None:
        if self.__zync_mode__ is zyncio.SYNC:
            self.sock.sendall(data)
        else:
            loop = asyncio.get_running_loop()
            await loop.sock_sendall(self.sock, data)

    @zyncio.zmethod
    async def recv_msg(self, n: int) -> bytes:
        buf = b''
        if self.__zync_mode__ is zyncio.SYNC:
            while len(buf) < n:
                buf += self.sock.recv(n)
        else:
            loop = asyncio.get_running_loop()
            while len(buf) < n:
                buf += await loop.sock_recv(self.sock, n)
        return buf

    @zyncio.zmethod
    async def do_handshake(self) -> None:
        await self.send_msg.zync(HANDSHAKE_REQ)
        response = await self.recv_msg.zync(len(HANDSHAKE_RESP))
        if response != HANDSHAKE_RESP:
            raise RuntimeError('Handshake failed')

    @zyncio.zproperty
    async def status(self) -> str:
        await self.send_msg.zync(STATUS_REQ)
        return (await self.recv_msg.zync(STATUS_RESP_LEN)).decode()


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
```

## Typing

ZyncIO is fully typed, and built specifically for typed projects. If you're getting
unexepcted type checking errors, please [open an issue](https://github.com/BenjyWiener/zyncio/issues).

## License

`zyncio` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
