"""A test client."""

from typing_extensions import Self

import zync

from .utils import assert_no_running_loop, assert_running_loop


class BaseClient:
    """A basic zync-based client."""

    @zync.zmethod
    async def simple_zmethod(self, zync_mode: zync.Mode, x: int) -> int:
        """Return `x` unchanged."""
        if zync_mode is zync.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        return x

    @zync.zmethod
    async def nested_zmethod(self, zync_mode: zync.Mode, x: int) -> int:
        """Return `x` unchanged by calling through to `simple_zmethod`."""
        return await self.simple_zmethod.run_zync(zync_mode, x)

    @zync.zproperty
    async def simple_zproperty(self, zync_mode: zync.Mode) -> zync.Mode:
        """Return the zync mode."""
        return zync_mode

    @zync.zclassmethod
    @classmethod
    async def class_method(cls, zync_mode: zync.Mode) -> type[Self]:
        """Return the class the method was called on."""
        if zync_mode is zync.SYNC:
            assert_no_running_loop()
        else:
            assert_running_loop()

        return cls

    @zync.zclassmethod
    @classmethod
    async def nested_class_method(cls, zync_mode: zync.Mode) -> type[Self]:
        """Return the class the method was called on by calling through to `class_method`."""
        return await cls.class_method.run_zync(zync_mode)


class SyncClient(BaseClient, zync.SyncMixin):
    """A sync client."""


class AsyncClient(BaseClient, zync.AsyncMixin):
    """An async client."""
