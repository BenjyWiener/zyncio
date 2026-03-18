"""A test client."""

from collections.abc import AsyncGenerator, Iterable
from typing import Generic, TypeVar
from typing_extensions import Self

import zyncio

from .utils import assert_no_running_loop, assert_running_loop


class BaseClient(zyncio.ZyncBase):
    """A basic zyncio-based client."""

    @zyncio.zmethod
    async def simple_zmethod(self, x: int) -> int:
        """Return `x` unchanged."""
        if self.__zync_mode__ is zyncio.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        return x

    @zyncio.zmethod
    async def nested_zmethod(self, x: int) -> int:
        """Return `x` unchanged by calling through to `simple_zmethod`."""
        return await self.simple_zmethod.zync(x)

    @zyncio.zproperty
    async def simple_zproperty(self) -> zyncio.Mode:
        """Return the zyncio mode."""
        return self.__zync_mode__

    @zyncio.zproperty
    async def nested_property(self) -> zyncio.Mode:
        """Return the zyncio mode by calling through to `simple_property`."""
        return await type(self).simple_zproperty(self)

    _settable_zproperty: int = 0

    @zyncio.zproperty
    async def _settable_zproperty_getter(self) -> int:
        """Return the zyncio mode."""
        if self.__zync_mode__ is zyncio.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        return self._settable_zproperty

    @_settable_zproperty_getter.setter
    async def settable_zproperty(self, value: int) -> None:
        """Set the zyncio mode."""
        if self.__zync_mode__ is zyncio.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        self._settable_zproperty = value

    @zyncio.zclassmethod
    @classmethod
    async def class_method(cls) -> type[Self]:
        """Return the class the method was called on."""
        if cls.__zync_mode__ is zyncio.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        return cls

    @zyncio.zclassmethod
    @classmethod
    async def nested_class_method(cls) -> type[Self]:
        """Return the class the method was called on by calling through to `class_method`."""
        return await cls.class_method.zync()

    @zyncio.zcontextmanagermethod
    async def context_manager(self, x: int) -> AsyncGenerator[int]:
        """Yield `x` unchanged."""
        yield x

    @zyncio.zcontextmanagermethod
    async def nested_context_manager(self, x: int) -> AsyncGenerator[int]:
        """Yield `x` unchanged by calling through to to `context_manager`."""
        async with self.context_manager.zync(x) as y:
            yield y

    @zyncio.zgeneratormethod
    async def generator_with_send(self, factor: int) -> AsyncGenerator[int, int]:
        """Yield sent values multiplied by factor until `0` is sent."""
        number = yield 0
        while number := (yield (number * factor)):
            pass

    @zyncio.zgeneratormethod
    async def nested_generator(self, factor: int, numbers: Iterable[int]) -> AsyncGenerator[int]:
        """Yield numbers from `numbers` multiplied by `factor` by calling through to `generator_with_send`."""
        gen = self.generator_with_send.zync(factor)
        await anext(gen)  # Prime the generator
        for n in numbers:
            yield await gen.asend(n)

        try:
            await gen.asend(0)
        except StopAsyncIteration:
            await gen.aclose()

    @property
    def user(self) -> 'ClientUser[Self]':
        """Get a `ClientUser` bound to `self`."""
        return ClientUser(self)


class SyncClient(zyncio.SyncMixin, BaseClient):
    """A sync client."""


class AsyncClient(zyncio.AsyncMixin, BaseClient):
    """An async client."""


ClientT = TypeVar('ClientT', bound=BaseClient)


class ClientUser(Generic[ClientT]):
    """A class that uses a client, for testing `__zync_proxy__`."""

    def __init__(self, client: ClientT) -> None:
        """Initialize the client user."""
        self.client: ClientT = client

    def __zync_proxy__(self) -> ClientT:
        return self.client

    @zyncio.zmethod
    async def use(self, x: int) -> int:
        """Return `x` unchanged by calling through to `self.client.simple_zmethod`."""
        return await self.client.simple_zmethod.zync(x)
