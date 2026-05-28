"""Unit tests for zyncio."""

import abc
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


def test_zfunc_sync(rand_int: int) -> None:
    """Test `zfunc.call_sync`."""
    assert _simple_zfunc.call_sync(rand_int) == rand_int


def test_zfunc_async(rand_int: int) -> None:
    """Test `zfunc.call_async`."""
    assert asyncio.run(_simple_zfunc.call_async(rand_int)) == rand_int


def test_zfunc_zync(rand_int: int) -> None:
    """Test `zfunc.call_zync`."""
    assert asyncio.run(_simple_zfunc.call_zync(zyncio.ASYNC, rand_int)) == rand_int


def test_invalid_zfunc() -> None:
    """Test calling a `zfunc` that awaits non-coroutines in sync mode."""

    @zyncio.zfunc
    async def invalid_func(zync_mode: zyncio.Mode) -> None:
        await asyncio.sleep(1)

    async def async_wrapper() -> None:
        # Run `invalid_func` with a running event loop, so we can test that `zyncio` raises an
        # exception, instead of `asyncio.sleep` complaining about no running loop.
        invalid_func.call_sync()

    with pytest.raises(RuntimeError, match=r'sync mode'):
        asyncio.run(async_wrapper())


def test_abstract_zmethod() -> None:
    """Test that instantiating an ABC with an abstract `zmethod`fails."""

    class Abstract(abc.ABC):
        @zyncio.zmethod
        @abc.abstractmethod
        async def abstract(self) -> None: ...  # pragma: no cover

    with pytest.raises(TypeError, match=r'abstract method'):
        Abstract()  # type: ignore[x-pyrefly,x-ty]

    class Concrete(Abstract):
        @zyncio.zmethod
        async def abstract(self) -> None: ...  # pragma: no cover

    Concrete()


def test_zmethod_sync(rand_int: int) -> None:
    """Test `zmethod` on a sync client."""
    client = SyncClient()
    assert client.simple_method(rand_int) == rand_int


def test_zmethod_async(rand_int: int) -> None:
    """Test `zmethod` on an async client."""
    client = AsyncClient()
    assert asyncio.run(client.simple_method(rand_int)) == rand_int


def test_zmethod_no_mixin(rand_int: int) -> None:
    """Test that calling a `zmethod` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.simple_method(rand_int)  # type: ignore


def test_zmethod_get_from_class() -> None:
    """Test that accessing a `zmethod` from a class returns the unbound `zmethod` object."""
    assert isinstance(BaseClient.simple_method, zyncio.zmethod)
    assert isinstance(SyncClient.simple_method, zyncio.zmethod)


def test_nested_zmethod_sync(rand_int: int) -> None:
    """Test nested `zmethod` on a sync client."""
    client = SyncClient()
    assert client.nested_method(rand_int) == rand_int


def test_nested_zmethod_async(rand_int: int) -> None:
    """Test nested `zmethod` on an async client."""
    client = AsyncClient()
    assert asyncio.run(client.nested_method(rand_int)) == rand_int


def test_generic_self_zmethod_sync() -> None:
    """Test a generic-over-self `zmethod` on a sync client."""
    client = SyncClient()
    assert client.generic_self_method() is client


def test_generic_self_zmethod_async() -> None:
    """Test a generic-over-self `zmethod` on an async client."""
    client = AsyncClient()
    assert asyncio.run(client.generic_self_method()) is client


def test_overloaded_method_with_make_sync() -> None:
    """Test `make_sync` on an overloaded method."""
    client = SyncClient()
    assert client.overloaded_method(True) is client  # ty: ignore  # zuban: ignore
    assert client.overloaded_method(False) is None  # zuban: ignore


def test_zproperty_sync() -> None:
    """Test `zproperty` on a sync client."""
    client = SyncClient()
    assert client.simple_property == zyncio.SYNC


def test_zproperty_async() -> None:
    """Test `zproperty` on an async client."""
    client = AsyncClient()
    assert asyncio.run(client.simple_property()) == zyncio.ASYNC


def test_zproperty_no_mixin() -> None:
    """Test that accessing a `zproperty` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.simple_property  # type: ignore[x-ty]


def test_zproperty_get_from_class() -> None:
    """Test that accessing a `zproperty` from a class returns the unbound `zproperty` object."""
    assert isinstance(BaseClient.simple_property, zyncio.zproperty)
    assert isinstance(SyncClient.simple_property, zyncio.zproperty)
    assert isinstance(AsyncClient.simple_property, zyncio.zproperty)


def test_nested_zproperty_sync() -> None:
    """Test a nested `zproperty` on a sync client."""
    client = SyncClient()
    assert client.nested_property == zyncio.SYNC


def test_nested_zproperty_async() -> None:
    """Test a nested `zproperty` on an async client."""
    client = AsyncClient()
    assert asyncio.run(client.simple_property()) == zyncio.ASYNC


def test_settable_zproperty_sync() -> None:
    """Test `ZyncSettableProperty` on a sync client."""
    client = SyncClient()
    initial_value = client.settable_property
    new_value = initial_value + 1
    client.settable_property = new_value
    assert client.settable_property == new_value


@pytest.mark.asyncio
async def test_settable_zproperty_async() -> None:
    """Test `ZyncSettableProperty` on an async client."""
    client = AsyncClient()
    initial_value = await client.settable_property()
    new_value = initial_value + 1
    await client.settable_property.set(new_value)
    assert await client.settable_property() == new_value

    with pytest.raises(TypeError, match=r'async mode'):
        client.settable_property = new_value  # type: ignore


def test_settable_zproperty_no_mixin() -> None:
    """Test that accessing a `ZyncSettableProperty` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.settable_property  # type: ignore[x-ty]


def test_settable_zproperty_get_from_class() -> None:
    """Test that accessing a `ZyncSettableProperty` from a class returns the unbound `ZyncSettableProperty` object."""
    assert isinstance(BaseClient.settable_property, zyncio.ZyncSettableProperty)
    assert isinstance(SyncClient.settable_property, zyncio.ZyncSettableProperty)
    assert isinstance(AsyncClient.settable_property, zyncio.ZyncSettableProperty)


def test_zclassmethod_sync(rand_int: int) -> None:
    """Test `zclassmethod` on a sync client."""
    assert SyncClient.simple_class_method(rand_int) == rand_int


def test_zclassmethod_async(rand_int: int) -> None:
    """Test `zclassmethod` on an async client."""
    assert asyncio.run(AsyncClient.simple_class_method(rand_int)) == rand_int


def test_zclassmethod_no_mixin() -> None:
    """Test that calling a `zclassmethod` raises if no mixin is used."""
    with pytest.raises(TypeError, match=r'Mixin'):
        BaseClient.simple_class_method(0)  # type: ignore


def test_nested_zclassmethod_sync(rand_int: int) -> None:
    """Test a nested `zclassmethod` on a sync client."""
    assert SyncClient.nested_class_method(rand_int) == rand_int


def test_nested_zclassmethod_async(rand_int: int) -> None:
    """Test a nested `zclassmethod` on an async client."""
    assert asyncio.run(AsyncClient.nested_class_method(rand_int)) == rand_int


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
    async with context_manager.call_zync(zync_mode, x) as y:
        yield y


def test_zcontextmanager_sync(rand_int: int) -> None:
    """Test `zcontextmanager.call_sync`."""
    with context_manager.call_sync(rand_int) as val:
        assert rand_int == val


@pytest.mark.asyncio
async def test_zcontextmanager_async(rand_int: int) -> None:
    """Test `zcontextmanager.call_async`."""
    async with context_manager.call_async(rand_int) as val:
        assert rand_int == val


def test_zcontextmanager_sync_caught_exception(rand_int: int) -> None:
    """Test `zcontextmanager.call_sync` with an exception that should be caught."""
    with context_manager.call_sync(rand_int) as val:
        assert rand_int == val
        raise CatchMe


@pytest.mark.asyncio
async def test_zcontextmanager_async_caught_exception(rand_int: int) -> None:
    """Test `zcontextmanager.call_async` with an exception that should be caught."""
    async with context_manager.call_async(rand_int) as val:
        assert rand_int == val
        raise CatchMe


def test_zcontextmanager_sync_uncaught_exception(rand_int: int) -> None:
    """Test `zcontextmanager.call_sync` with an exception that should not be caught."""
    with pytest.raises(DontCatchMe):
        with context_manager.call_sync(rand_int) as val:
            assert rand_int == val
            raise DontCatchMe


@pytest.mark.asyncio
async def test_zcontextmanager_async_uncaught_exception(rand_int: int) -> None:
    """Test `zcontextmanager.call_async` with an exception that should not be caught."""
    with pytest.raises(DontCatchMe):
        async with context_manager.call_async(rand_int) as val:
            assert rand_int == val
            raise DontCatchMe


def test_nested_zcontextmanager_sync(rand_int: int) -> None:
    """Test `zcontextmanager.call_sync` with a nested `zcontextmanager`."""
    with nested_context_manager.call_sync(rand_int) as val:
        assert rand_int == val


@pytest.mark.asyncio
async def test_nested_zcontextmanager_async(rand_int: int) -> None:
    """Test `zcontextmanager.call_async` with a nested `zcontextmanager`."""
    async with nested_context_manager.call_async(rand_int) as val:
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


@pytest.mark.asyncio
async def test_zcontextmanagermethod_zync(rand_int: int) -> None:
    """Test `zcontextmanagermethod.z`."""
    async_client = AsyncClient()
    async with async_client.context_manager.z(rand_int) as val:
        assert rand_int == val


def test_zcontextmanagermethod_no_mixin() -> None:
    """Test that calling a `zcontextmanagermethod` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.context_manager()  # type: ignore


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


@zyncio.zgenerator
async def simple_generator(zync_mode: zyncio.Mode, *args: int) -> AsyncGenerator[int]:
    """Yield arguments unchanged."""
    for arg in args:
        yield arg


def test_zgenerator_sync() -> None:
    """Test `zgenerator.call_sync`."""
    numbers = random.choices(range(1, 100), k=10)
    assert [*simple_generator.call_sync(*numbers)] == numbers


@pytest.mark.asyncio
async def test_zgenerator_async() -> None:
    """Test `zgenerator.call_async`."""
    numbers = random.choices(range(1, 100), k=10)
    assert [n async for n in simple_generator.call_async(*numbers)] == numbers


@pytest.mark.asyncio
async def test_zgenerator_zync() -> None:
    """Test `zgenerator.call_zync`."""
    numbers = random.choices(range(1, 100), k=10)
    assert [n async for n in simple_generator.call_zync(zyncio.ASYNC, *numbers)] == numbers


@zyncio.zgenerator
async def generator_with_send(zync_mode: zyncio.Mode, factor: int) -> AsyncGenerator[int, int]:
    """Yield sent values multiplied by factor until `0` is sent."""
    number = yield 0
    while number := (yield (number * factor)):
        pass


def test_zgenerator_with_send_sync(rand_int: int) -> None:
    """Test `zgenerator` with `send` in sync mode."""
    numbers = random.choices(range(1, 100), k=10)
    gen = generator_with_send.call_sync(rand_int)
    next(gen)  # Prime the generator
    for n in numbers:
        assert gen.send(n) == n * rand_int

    with pytest.raises(StopIteration):
        gen.send(0)


@pytest.mark.asyncio
async def test_zgenerator_with_send_async(rand_int: int) -> None:
    """Test `zgenerator` with `send` in async mode."""
    numbers = random.choices(range(1, 100), k=10)
    gen = generator_with_send.call_async(rand_int)
    await anext(gen)  # Prime the generator
    for n in numbers:
        assert await gen.asend(n) == n * rand_int

    with pytest.raises(StopAsyncIteration):
        await gen.asend(0)


def test_nested_zgeneratormethod_sync(rand_int: int) -> None:
    """Test a nested `zgeneratormethod` on a sync client."""
    client = SyncClient()
    numbers = random.choices(range(1, 100), k=10)
    assert [*client.nested_generator(rand_int, numbers)] == [rand_int * n for n in numbers]


@pytest.mark.asyncio
async def test_nested_zgeneratormethod_async(rand_int: int) -> None:
    """Test a nested `zgeneratormethod` on an async client."""
    client = AsyncClient()
    numbers = random.choices(range(1, 100), k=10)
    assert [n async for n in client.nested_generator(rand_int, numbers)] == [rand_int * n for n in numbers]


@pytest.mark.asyncio
async def test_zgeneratormethod_zync(rand_int: int) -> None:
    """Test `zgeneratormethod._`."""
    client = AsyncClient()
    numbers = random.choices(range(1, 100), k=10)
    assert [n async for n in client.nested_generator.z(rand_int, numbers)] == [rand_int * n for n in numbers]


def test_zgeneratormethod_no_mixin() -> None:
    """Test that calling a `zgeneratormethod` raises if no mixin is used."""
    client = BaseClient()
    with pytest.raises(TypeError, match=r'Mixin'):
        client.generator_with_send()  # type: ignore


def test_zgeneratormethod_get_from_class() -> None:
    """Test that accessing a `zgeneratormethod` from a class returns the unbound `zgeneratormethod` object."""
    assert isinstance(BaseClient.generator_with_send, zyncio.zgeneratormethod)
    assert isinstance(SyncClient.generator_with_send, zyncio.zgeneratormethod)


def test_zync_delegate_sync(rand_int: int) -> None:
    """Test `zyncio.ZyncDelegator` functionality with a sync client."""
    client = SyncClient()
    assert client.user.use(rand_int) == rand_int


@pytest.mark.asyncio
async def test_zync_delegate_async(rand_int: int) -> None:
    """Test `zyncio.ZyncDelegator` functionality with an async client."""
    client = AsyncClient()
    assert await client.user.use(rand_int) == rand_int


def test_zync_nested_delegate_sync(rand_int: int) -> None:
    """Test nested `zyncio.ZyncDelegator` functionality with a sync client."""
    client = SyncClient()
    assert client.user.user.use(rand_int) == rand_int


def test_zync_delegate_caching() -> None:
    """Test that `zyncio.get_mode` caches the mode of a `ZyncDelegator` object."""

    class Delegator:
        call_count: int = 0

        def __zync_delegate__(self) -> SyncClient:
            self.call_count += 1
            return SyncClient()

    delegator = Delegator()

    assert zyncio.get_mode(delegator) is zyncio.SYNC
    assert zyncio.get_mode(delegator) is zyncio.SYNC

    assert delegator.call_count == 1


def test_zync_delegate_caching_failure() -> None:
    """Test that `zyncio.get_mode` doesn't raise when caching fails."""

    class Delegator:
        __slots__ = ('call_count',)

        def __init__(self) -> None:
            self.call_count: int = 0

        def __zync_delegate__(self) -> SyncClient:
            self.call_count += 1
            return SyncClient()

    delegator = Delegator()

    assert zyncio.get_mode(delegator) is zyncio.SYNC
    assert zyncio.get_mode(delegator) is zyncio.SYNC

    assert delegator.call_count == 2


@pytest.mark.asyncio
async def test_zync_nested_delegate_async(rand_int: int) -> None:
    """Test nested `zyncio.ZyncDelegator` functionality with an async client."""
    client = AsyncClient()
    assert await client.user.user.use(rand_int) == rand_int


def test_type_guards(rand_int: int) -> None:
    """Test the `is_sync`, `is_async`, `is_sync_class`, and `is_async_class` type guards."""
    clients: list[BaseClient] = [BaseClient(), SyncClient(), AsyncClient()]
    for client in clients:
        if zyncio.is_sync(client):
            assert (
                # pyrefly: ignore
                client.simple_method(rand_int) == rand_int  # zuban: ignore
            )
        elif zyncio.is_async(client):
            # pyrefly: ignore
            assert asyncio.run(client.simple_method(rand_int)) == rand_int  # zuban: ignore
        else:
            pass

    client_classes: list[type[BaseClient]] = [BaseClient, SyncClient, AsyncClient]
    for client_class in client_classes:
        if zyncio.is_sync_class(client_class):
            # pyrefly: ignore
            assert client_class.simple_class_method(rand_int) == rand_int  # ty: ignore
        elif zyncio.is_async_class(client_class):
            # pyrefly: ignore
            assert asyncio.run(client_class.simple_class_method(rand_int)) == rand_int  # ty: ignore
        else:
            pass
