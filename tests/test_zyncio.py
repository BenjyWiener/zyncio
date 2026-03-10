"""Unit tests for zyncio."""

import asyncio
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
    """Test `zclassmethod` on a sync client."""
    assert SyncClient.nested_class_method() is SyncClient


def test_nested_zclassmethod_async() -> None:
    """Test `zclassmethod` on an async client."""
    assert asyncio.run(AsyncClient.nested_class_method()) is AsyncClient
