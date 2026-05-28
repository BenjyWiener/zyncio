"""Typing tests for zyncio.

This file (as well as the other files under tests/) is expected to type check without any errors.
The tests are designed to ensure that valid usages have correct types inferred,
and that invalid usages produce type errors.

Expected errors are marked with `# type: ignore` comments; type checkers should be configured to report unused ignores.

Lines that pass Pyright (our current "first-class" type checker) but fail other type checkers should be marked with the
type checker-specific ignore comment.

Expected errors *not* caught by a specific type checker should be marked `# type: ignore[x-checker-name]`. For multiple
checkers, a comma-separated list should be used (ex: `# type: ignore[x-mypy,x-ty]`).

See ../run_typing_tests.py for details on how files are pre-processed before checking is performed.
"""
# ruff: noqa: D101, D102

from collections.abc import AsyncGenerator
from typing_extensions import assert_type

import zyncio

from .client import AsyncClient, BaseClient, SyncClient


base_client = BaseClient()
sync_client = SyncClient()
async_client = AsyncClient()


async def _() -> None:  # Allow using `await`
    base_client.simple_method(1)  # type: ignore
    assert_type(await base_client.simple_method.z(1), int)
    assert_type(sync_client.simple_method(1), int)
    assert_type(await async_client.simple_method(1), int)
    assert_type(sync_client.generic_self_method(), SyncClient)  # mypy: ignore  # ty: ignore
    assert_type(await async_client.generic_self_method(), AsyncClient)  # mypy: ignore  # ty: ignore

    base_client.simple_property  # type: ignore[x-ty]
    assert_type(sync_client.simple_property, zyncio.Mode | None)
    assert_type(await async_client.simple_property(), zyncio.Mode | None)

    base_client.settable_property  # type: ignore[x-ty]
    assert_type(sync_client.settable_property, int)
    sync_client.settable_property = 1
    assert_type(await async_client.settable_property(), int)
    await async_client.settable_property.set(1)
    # This test needs to come last, since the assignment messes with the inferred
    # type of `async_client.settable_zproperty`.
    async_client.settable_property = 1  # type: ignore

    base_client.simple_class_method(1)  # type: ignore
    assert_type(SyncClient.simple_class_method(1), int)  # zuban: ignore
    assert_type(await AsyncClient.simple_class_method(1), int)  # zuban: ignore

    base_client.context_manager()  # type: ignore
    with sync_client.context_manager(1) as x:
        assert_type(x, int)
    async with async_client.context_manager(1) as x:
        assert_type(x, int)

    base_client.nested_generator()  # type: ignore
    for n in sync_client.nested_generator(1, (1,)):
        assert_type(n, int)
    async for n in async_client.nested_generator(1, (1,)):
        assert_type(n, int)

    base_client.user.use()  # type: ignore
    assert_type(sync_client.user.use(1), int)
    assert_type(await async_client.user.use(1), int)

    base_client.user.user.use()  # type: ignore
    assert_type(sync_client.user.user.use(1), int)
    assert_type(await async_client.user.user.use(1), int)

    assert_type(sync_client.overloaded_method(True), SyncClient)  # ty: ignore  # zuban: ignore
    assert_type(sync_client.overloaded_method(False), None)  # ty: ignore  # zuban: ignore
    assert_type(await async_client.overloaded_method(True), AsyncClient)  # ty: ignore
    assert_type(await async_client.overloaded_method(False), None)


# Check that overriding `zmethod` etc. is allowed.
class Parent:
    @zyncio.zmethod
    async def method(self) -> None: ...

    @zyncio.zclassmethod
    @classmethod
    async def classmethod(cls) -> None: ...  # zuban: ignore

    @zyncio.zproperty
    async def property(self) -> None: ...

    @zyncio.zcontextmanagermethod
    async def contextmanagermethod(self) -> AsyncGenerator[None]:
        yield

    @zyncio.zgeneratormethod
    async def generatormethod(self) -> AsyncGenerator[None]:
        yield


class Child(Parent):
    @zyncio.zmethod
    async def method(self) -> None: ...

    @zyncio.zclassmethod
    @classmethod
    async def classmethod(cls) -> None: ...  # zuban: ignore

    @zyncio.zproperty
    async def property(self) -> None: ...

    @zyncio.zcontextmanagermethod
    async def contextmanagermethod(self) -> AsyncGenerator[None]:
        yield

    @zyncio.zgeneratormethod
    async def generatormethod(self) -> AsyncGenerator[None]:
        yield
