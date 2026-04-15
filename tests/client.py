"""A test client."""

from collections.abc import AsyncGenerator, Iterable
from typing import Generic, Literal, TypeVar, overload
from typing_extensions import Self

import zyncio

from .utils import assert_no_running_loop, assert_running_loop


class BaseClient:
    """A basic zyncio-based client."""

    @zyncio.zmethod
    async def simple_zmethod(self, x: int) -> int:
        """Return `x` unchanged."""
        if zyncio.is_sync(self):
            assert_no_running_loop()
        else:
            assert_running_loop()

        return x

    @zyncio.zmethod
    async def nested_zmethod(self, x: int) -> int:
        """Return `x` unchanged by calling through to `simple_zmethod`."""
        return await self.simple_zmethod.z(x)

    @zyncio.zproperty
    async def simple_zproperty(self) -> zyncio.Mode | None:
        """Return the zyncio mode."""
        return zyncio.get_mode(self)

    @zyncio.zproperty
    async def nested_property(self) -> zyncio.Mode | None:
        """Return the zyncio mode by calling through to `simple_property`."""
        return await type(self).simple_zproperty(self)

    _settable_zproperty: int = 0

    @zyncio.zproperty
    async def _settable_zproperty_getter(self) -> int:
        """Return the zyncio mode."""
        if zyncio.is_sync(self):
            assert_no_running_loop()
        else:
            assert_running_loop()

        return self._settable_zproperty

    @_settable_zproperty_getter.setter
    async def settable_zproperty(self, value: int) -> None:
        """Set the zyncio mode."""
        if zyncio.is_sync(self):
            assert_no_running_loop()
        else:
            assert_running_loop()

        self._settable_zproperty = value

    @zyncio.zclassmethod
    @classmethod
    async def class_method(cls) -> type[Self]:
        """Return the class the method was called on."""
        if zyncio.is_sync_class(cls):
            assert_no_running_loop()
        else:
            assert_running_loop()

        return cls

    @zyncio.zclassmethod
    @classmethod
    async def nested_class_method(cls) -> type[Self]:
        """Return the class the method was called on by calling through to `class_method`."""
        return await cls.class_method.z()

    @zyncio.zcontextmanagermethod
    async def context_manager(self, x: int) -> AsyncGenerator[int]:
        """Yield `x` unchanged."""
        yield x

    @zyncio.zcontextmanagermethod
    async def nested_context_manager(self, x: int) -> AsyncGenerator[int]:
        """Yield `x` unchanged by calling through to to `context_manager`."""
        async with self.context_manager.z(x) as y:
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
        gen = self.generator_with_send.z(factor)
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


ClientT_co = TypeVar('ClientT_co', bound=BaseClient, covariant=True)


@overload
async def overloaded_method(self: ClientT_co, return_self: Literal[True]) -> ClientT_co: ...
@overload
async def overloaded_method(self, return_self: Literal[False]) -> None: ...
async def overloaded_method(self: ClientT_co, return_self: bool) -> ClientT_co | None:
    """Return `self` iff `return_self` is `True`, otherwise return `None`."""
    if return_self:
        return self


class SyncClient(BaseClient, zyncio.SyncMixin):
    """A sync client."""

    overloaded_method = zyncio.make_sync(overloaded_method)


class AsyncClient(BaseClient, zyncio.AsyncMixin):
    """An async client."""

    overloaded_method = overloaded_method


class ClientUser(Generic[ClientT_co]):
    """A class that uses a client, for testing `zyncio.ZyncDelegator`."""

    def __init__(self, client: ClientT_co) -> None:
        """Initialize the client user."""
        self.client: ClientT_co = client

    def __zync_delegate__(self) -> ClientT_co:
        return self.client

    @zyncio.zmethod
    async def use(self, x: int) -> int:
        """Return `x` unchanged by calling through to `self.client.simple_zmethod`."""
        return await self.client.simple_zmethod.z(x)

    @property
    def user(self) -> 'ClientUserUser[Self]':
        """Get a `ClientUser` bound to `self`."""
        return ClientUserUser(self)


ClientUserT_co = TypeVar('ClientUserT_co', bound=ClientUser[BaseClient])


class ClientUserUser(Generic[ClientUserT_co]):
    """A class that uses a client user, for testing `zyncio.ZyncDelegator` with nested delegation."""

    def __init__(self, client_user: ClientUserT_co) -> None:
        """Initialize the client user user."""
        self.client_user: ClientUserT_co = client_user

    def __zync_delegate__(self) -> ClientUserT_co:
        return self.client_user

    @zyncio.zmethod
    async def use(self, x: int) -> int:
        """Return `x` unchanged by calling through to `self.client_user.use`."""
        return await self.client_user.use.z(x)
