"""A test client."""

from collections.abc import AsyncGenerator
from typing_extensions import Self

import zyncio

from .utils import assert_no_running_loop, assert_running_loop


class BaseClient:
    """A basic zyncio-based client."""

    @zyncio.zmethod
    async def simple_zmethod(self, zync_mode: zyncio.Mode, x: int) -> int:
        """Return `x` unchanged."""
        if zync_mode is zyncio.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        return x

    @zyncio.zmethod
    async def nested_zmethod(self, zync_mode: zyncio.Mode, x: int) -> int:
        """Return `x` unchanged by calling through to `simple_zmethod`."""
        return await self.simple_zmethod[zync_mode](x)

    @zyncio.zproperty
    async def simple_zproperty(self, zync_mode: zyncio.Mode) -> zyncio.Mode:
        """Return the zyncio mode."""
        return zync_mode

    _settable_zproperty: int = 0

    @zyncio.zproperty
    async def _settable_zproperty_getter(self, zync_mode: zyncio.Mode) -> int:
        """Return the zyncio mode."""
        if zync_mode is zyncio.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        return self._settable_zproperty

    @_settable_zproperty_getter.setter
    async def settable_zproperty(self, zync_mode: zyncio.Mode, value: int) -> None:
        """Set the zyncio mode."""
        if zync_mode is zyncio.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        self._settable_zproperty = value

    @zyncio.zclassmethod
    @classmethod
    async def class_method(cls, zync_mode: zyncio.Mode) -> type[Self]:
        """Return the class the method was called on."""
        if zync_mode is zyncio.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        return cls

    @zyncio.zclassmethod
    @classmethod
    async def nested_class_method(cls, zync_mode: zyncio.Mode) -> type[Self]:
        """Return the class the method was called on by calling through to `class_method`."""
        return await cls.class_method[zync_mode]()

    @zyncio.zcontextmanagermethod
    async def context_manager(self, zync_mode: zyncio.Mode, x: int) -> AsyncGenerator[int]:
        """Yield `x` unchanged."""
        yield x

    @zyncio.zcontextmanagermethod
    async def nested_context_manager(self, zync_mode: zyncio.Mode, x: int) -> AsyncGenerator[int]:
        """Yield `x` unchanged by calling through to to `context_manager`."""
        async with self.context_manager[zync_mode](x) as y:
            yield y


class SyncClient(BaseClient, zyncio.SyncMixin):
    """A sync client."""


class AsyncClient(BaseClient, zyncio.AsyncMixin):
    """An async client."""
