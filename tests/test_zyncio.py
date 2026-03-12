"""Unit tests for zyncio."""

import asyncio
from collections.abc import AsyncGenerator
import random

import pytest

import zyncio

from .client import AsyncClient, BaseClient, SyncClient
from .utils import assert_no_running_loop, assert_running_loop


@pytest.fixture
def rand_int() -> int:
    """Return a random integer."""
    return random.randint(1, 100)


@zyncio.zfunc
async def _simple_zfunc(zync_mode: zyncio.Mode, x: int) -> int:
    if zync_mode is zyncio.SYNC:
        assert_no_running_loop()
    else:
        assert_running_loop()

    return x


def test_zfunc_run_sync(rand_int: int) -> None:
    """Test `zfunc.run_sync`."""
    assert _simple_zfunc.run_sync(rand_int) == rand_int


def test_zfunc_run_async(rand_int: int) -> None:
    """Test `zfunc.run_async`."""
    assert asyncio.run(_simple_zfunc.run_async(rand_int)) == rand_int


def test_invalid_zfunc() -> None:
    """Test calling a `zfunc` that awaits non-coroutines in sync mode."""

    @zyncio.zfunc
    async def invalid_func(zync_mode: zyncio.Mode) -> None:
        await asyncio.sleep(1)

    async def async_wrapper() -> None:
        # Run `invalid_func` with a running event loop, so we can test that `zyncio` raises an
        # exception, instead of `asyncio.sleep` complaining about no running loop.
        invalid_func.run_sync()

    with pytest.raises(RuntimeError, match=r'sync mode'):
        asyncio.run(async_wrapper())


def test_zmethod_sync(rand_int: int) -> None:
    """Test `zmethod` on a sync client."""
    client = SyncClient()
    assert client.simple_zmethod(rand_int) == rand_int


def test_zmethod_async(rand_int: int) -> None:
    """Test `zmethod` on an async client."""
    client = AsyncClient()
    assert asyncio.run(client.simple_zmethod(rand_int)) == rand_int


def test_zmethod_no_mixin(rand_int: int) -> None:
    """Test that calling a `zmethod` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.simple_zmethod(rand_int)  # pyright: ignore[reportCallIssue]


def test_zmethod_get_from_class() -> None:
    """Test that accessing a `zmethod` from a class returns the unbound `zmethod` object."""
    assert isinstance(BaseClient.simple_zmethod, zyncio.zmethod)
    assert isinstance(SyncClient.simple_zmethod, zyncio.zmethod)


def test_nested_zmethod_sync(rand_int: int) -> None:
    """Test nested `zmethod` on a sync client."""
    client = SyncClient()
    assert client.nested_zmethod(rand_int) == rand_int


def test_nested_zmethod_async(rand_int: int) -> None:
    """Test nested `zmethod` on an async client."""
    client = AsyncClient()
    assert asyncio.run(client.nested_zmethod(rand_int)) == rand_int


def test_zproperty_sync() -> None:
    """Test `zproperty` on a sync client."""
    client = SyncClient()
    assert client.simple_zproperty == zyncio.SYNC


def test_zproperty_async() -> None:
    """Test `zproperty` on an async client."""
    client = AsyncClient()
    assert asyncio.run(client.simple_zproperty()) == zyncio.ASYNC


def test_zproperty_no_mixin() -> None:
    """Test that accessing a `zproperty` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.simple_zproperty  # pyright: ignore[reportAttributeAccessIssue]


def test_zproperty_get_from_class() -> None:
    """Test that accessing a `zproperty` from a class returns the unbound `zproperty` object."""
    assert isinstance(BaseClient.simple_zproperty, zyncio.zproperty)
    assert isinstance(SyncClient.simple_zproperty, zyncio.zproperty)
    assert isinstance(AsyncClient.simple_zproperty, zyncio.zproperty)


def test_settable_zproperty_sync() -> None:
    """Test `ZyncSettableProperty` on a sync client."""
    client = SyncClient()
    initial_value = client.settable_zproperty
    new_value = initial_value + 1
    client.settable_zproperty = new_value
    assert client.settable_zproperty == new_value


@pytest.mark.asyncio
async def test_settable_zproperty_async() -> None:
    """Test `ZyncSettableProperty` on an async client."""
    client = AsyncClient()
    initial_value = await client.settable_zproperty()
    new_value = initial_value + 1
    await client.settable_zproperty.set(new_value)
    assert await client.settable_zproperty() == new_value

    with pytest.raises(TypeError, match=r'Mixin'):
        client.settable_zproperty = new_value  # pyright: ignore[reportAttributeAccessIssue]


def test_settable_zproperty_no_mixin() -> None:
    """Test that accessing a `ZyncSettableProperty` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.settable_zproperty  # pyright: ignore[reportAttributeAccessIssue]


def test_settable_zproperty_get_from_class() -> None:
    """Test that accessing a `ZyncSettableProperty` from a class returns the unbound `ZyncSettableProperty` object."""
    assert isinstance(BaseClient.settable_zproperty, zyncio.ZyncSettableProperty)
    assert isinstance(SyncClient.settable_zproperty, zyncio.ZyncSettableProperty)
    assert isinstance(AsyncClient.settable_zproperty, zyncio.ZyncSettableProperty)


def test_zclassmethod_sync() -> None:
    """Test `zclassmethod` on a sync client."""
    assert SyncClient.class_method() is SyncClient


def test_zclassmethod_async() -> None:
    """Test `zclassmethod` on an async client."""
    assert asyncio.run(AsyncClient.class_method()) is AsyncClient


def test_zclassmethod_no_mixin() -> None:
    """Test that calling a `zclassmethod` raises if no mixin is used."""
    with pytest.raises(TypeError, match=r'Mixin'):
        BaseClient.class_method()  # pyright: ignore[reportCallIssue]


def test_nested_zclassmethod_sync() -> None:
    """Test a nested `zclassmethod` on a sync client."""
    assert SyncClient.nested_class_method() is SyncClient


def test_nested_zclassmethod_async() -> None:
    """Test a nested `zclassmethod` on an async client."""
    assert asyncio.run(AsyncClient.nested_class_method()) is AsyncClient


class CatchMe(Exception):
    """Exception to try catching."""


class DontCatchMe(Exception):
    """Exception to propogate."""


@zyncio.zcontextmanager
async def context_manager(zync_mode: zyncio.Mode, x: int) -> AsyncGenerator[int]:
    """Yield `x` unchanged, and catch `CatchMe` exceptions."""
    try:
        yield x
    except CatchMe:
        pass


@zyncio.zcontextmanager
async def nested_context_manager(zync_mode: zyncio.Mode, x: int) -> AsyncGenerator[int]:
    """Yield `x` unchanged by calling through to `context_manager`."""
    async with context_manager[zync_mode](x) as y:
        yield y


def test_zcontextmanager_sync(rand_int: int) -> None:
    """Test `zcontextmanager.enter_sync`."""
    with context_manager.enter_sync(rand_int) as val:
        assert rand_int == val


@pytest.mark.asyncio
async def test_zcontextmanager_async(rand_int: int) -> None:
    """Test `zcontextmanager.enter_async`."""
    async with context_manager.enter_async(rand_int) as val:
        assert rand_int == val


def test_zcontextmanager_sync_caught_exception(rand_int: int) -> None:
    """Test `zcontextmanager.enter_sync` with an exception that should be caught."""
    with context_manager.enter_sync(rand_int) as val:
        assert rand_int == val
        raise CatchMe


@pytest.mark.asyncio
async def test_zcontextmanager_async_caught_exception(rand_int: int) -> None:
    """Test `zcontextmanager.enter_async` with an exception that should be caught."""
    async with context_manager.enter_async(rand_int) as val:
        assert rand_int == val
        raise CatchMe


def test_zcontextmanager_sync_uncaught_exception(rand_int: int) -> None:
    """Test `zcontextmanager.enter_sync` with an exception that should not be caught."""
    with pytest.raises(DontCatchMe):
        with context_manager.enter_sync(rand_int) as val:
            assert rand_int == val
            raise DontCatchMe


@pytest.mark.asyncio
async def test_zcontextmanager_async_uncaught_exception(rand_int: int) -> None:
    """Test `zcontextmanager.enter_async` with an exception that should not be caught."""
    with pytest.raises(DontCatchMe):
        async with context_manager.enter_async(rand_int) as val:
            assert rand_int == val
            raise DontCatchMe


def test_nested_zcontextmanager_sync(rand_int: int) -> None:
    """Test `zcontextmanager.enter_sync` with a nested `zcontextmanager`."""
    with nested_context_manager.enter_sync(rand_int) as val:
        assert rand_int == val


@pytest.mark.asyncio
async def test_nested_zcontextmanager_async(rand_int: int) -> None:
    """Test `zcontextmanager.enter_async` with a nested `zcontextmanager`."""
    async with nested_context_manager.enter_async(rand_int) as val:
        assert rand_int == val


def test_zcontextmanagermethod_sync(rand_int: int) -> None:
    """Test `zcontextmanagermethod` on a sync client."""
    sync_client = SyncClient()
    with sync_client.context_manager(rand_int) as val:
        assert rand_int == val


@pytest.mark.asyncio
async def test_zcontextmanagermethod_async(rand_int: int) -> None:
    """Test `zcontextmanagermethod` on an async client."""
    async_client = AsyncClient()
    async with async_client.context_manager(rand_int) as val:
        assert rand_int == val


def test_zcontextmanagermethod_no_mixin() -> None:
    """Test that calling a `zcontextmanagermethod` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.context_manager()  # pyright: ignore[reportCallIssue]


def test_nested_zcontextmanagermethod_sync(rand_int: int) -> None:
    """Test a nested `zcontextmanagermethod` on a sync client."""
    client = SyncClient()
    with client.nested_context_manager(rand_int) as val:
        assert rand_int == val


@pytest.mark.asyncio
async def test_nested_zcontextmanagermethod_async(rand_int: int) -> None:
    """Test a nested `zcontextmanagermethod` on an async client."""
    client = AsyncClient()
    async with client.nested_context_manager(rand_int) as val:
        assert rand_int == val


def test_zcontextmanagermethod_get_from_class() -> None:
    """Test that accessing a `zcontextmanagermethod` from a class returns the unbound `zcontextmanagermethod` object."""
    assert isinstance(BaseClient.context_manager, zyncio.zcontextmanagermethod)
    assert isinstance(SyncClient.context_manager, zyncio.zcontextmanagermethod)
