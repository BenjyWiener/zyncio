"""A test client."""

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
        return await self.simple_zmethod.run_zync(zync_mode, x)

    @zyncio.zproperty
    async def simple_zproperty(self, zync_mode: zyncio.Mode) -> zyncio.Mode:
        """Return the zyncio mode."""
        return zync_mode

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
        return await cls.class_method.run_zync(zync_mode)


class SyncClient(BaseClient, zyncio.SyncMixin):
    """A sync client."""


class AsyncClient(BaseClient, zyncio.AsyncMixin):
    """An async client."""
