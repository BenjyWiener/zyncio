# `zync`

## Write dual sync/async interfaces with minimal duplication.

> If I had a nickel for every almost identical interface I had to write,
> I'd have two nickels... which isn't a lot, but it's weird that I had to
> write it twice.
>
> – Dr. Doofenshmirtz, before discovering zync.

# What is `zync`?

`zync` allows you to write interfaces that can be used synchronously and asynchronously,
while avoiding the code duplication this usually entails.

# How does it work?

`zync` works due to the fact that in Python you can actually run a coroutine **without an event loop**,
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
async def zync_sleep(zync_mode: zync.Mode, secs: float) -> None:
    if zync_mode is zync.SYNC:
        time.sleep(secs)
    else:
        await asyncio.sleep(secs)
```

But this isn't very convenient; you need to pass an additional parameter, and running in
sync mode is pretty clunky. That's where `zync.zfunc` comes in:

```python
@zync.zfunc
async def zync_sleep(zync_mode: zync.Mode, secs: float) -> None:
    ...

zync_sleep.run_sync(3)
asyncio.run(zync_sleep.run_async(3))

@zync.zfunc
async def sleep_3(zync_mode: zync.Mode) -> None:
    await zync_sleep.run_zync(zync_mode, 3)
```

## The real magic: `SyncMixin`/`AsyncMixin`, `zync.zmethod`, and `zync.zproperty`

The real power of `zync` comes out when implementing client interfaces:

1. Implement a single base client, using the `zync.zmethod` and `zync.zproperty`
   decorators.

2. Create two subclasses a sync client and an async client, adding the `zync.SyncMixin`
   and `zync.AsyncMixin` mixins respectively.

3. All of your `zync.zmethod`s magically become sync methods on the sync client and async
   methods on the async client.

   All of the `zync.zproperty`s magically become properties on the sync client, and async
   methods on the async client.

```python
class BaseClient:
    def __init__(self, sock: socket.socket) -> None:
        self.sock: socket.socket = sock

    @zync.zmethod
    async def send_msg(self, zync_mode: zync.Mode, data: bytes) -> None:
        if zync_mode is zync.SYNC:
            self.sock.sendall(data)
        else:
            loop = asyncio.get_running_loop()
            await loop.sock_sendall(self.sock, data)

    @zync.zmethod
    async def recv_msg(self, zync_mode: zync.Mode, n: int) -> bytes:
        buf = b''
        if zync_mode is zync.SYNC:
            while len(buf) < n:
                buf += self.sock.recv(n)
        else:
            loop = asyncio.get_running_loop()
            while len(buf) < n:
                buf += await loop.sock_recv(self.sock, n)
        return buf

    @zync.zmethod
    async def do_handshake(self, zync_mode: zync.Mode) -> None:
        await self.send_msg.run_zync(zync_mode, HANDSHAKE_REQ)
        response = await self.recv_msg.run_zync(zync_mode, len(HANDSHAKE_RESP))
        if response != HANDSHAKE_RESP:
            raise RuntimeError('Handshake failed')

    @zync.zproperty
    async def status(self, zync_mode: zync.Mode) -> str:
        await self.send_msg.run_zync(zync_mode, STATUS_REQ)
        return (await self.recv_msg.run_zync(zync_mode, STATUS_RESP_LEN)).decode()


class SyncClient(BaseClient, zync.SyncMixin):
    pass


class AsyncClient(BaseClient, zync.AsyncMixin):
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

# Typing

`zync` is fully typed, and built specifically for typed projects. If you're getting
unexepcted type checking errors, please [open an issue](https://github.com/BenjyWiener/zync/issues).
