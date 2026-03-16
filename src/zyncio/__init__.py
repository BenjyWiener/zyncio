"""Write dual sync/async interfaces with minimal duplication."""

from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from enum import Enum
from functools import cached_property, partial
import sys
from types import MethodType
from typing import Any, Concatenate, Final, Generic, Literal, ParamSpec, Protocol, TypeAlias, TypeVar, cast, overload
from typing_extensions import Self

import zyncio


__all__ = [
    'Mode',
    'SYNC',
    'ASYNC',
    'zfunc',
    'zmethod',
    'zclassmethod',
    'zproperty',
    'zcontextmanager',
    'zcontextmanagermethod',
    'SyncMixin',
    'AsyncMixin',
]


_UNKNOWN_FUNC_NAME: Final = '<unknown>'


class Mode(Enum):
    """`zyncio` execution mode."""

    SYNC = 'sync'
    ASYNC = 'async'


SYNC: Final = Mode.SYNC
ASYNC: Final = Mode.ASYNC

# NOTE: We use covariant `TypeVar`s in some places where we should technically use
# invariant ones (such as `zclassmethod`, which should use `SelfT`, not `SelfT_co`).
# Without this, some common accepted (although theoretically unsafe) patterns, such as
# overriding `classmethod`s and `property`s would be flagged by type checkers.
# In this case we've chosen convenience over correctness.
CallableT = TypeVar('CallableT', bound=Callable[..., Any])
P = ParamSpec('P')
ReturnT = TypeVar('ReturnT')
ReturnT_co = TypeVar('ReturnT_co', covariant=True)
YieldT = TypeVar('YieldT')
YieldT_co = TypeVar('YieldT_co', covariant=True)
SendT_contra = TypeVar('SendT_contra', contravariant=True)
SelfT = TypeVar('SelfT')
SelfT_co = TypeVar('SelfT_co', covariant=True)


Zyncable = Callable[Concatenate[Mode, P], Coroutine[Any, Any, ReturnT_co]]
ZyncableMethod = Callable[Concatenate[SelfT, Mode, P], Coroutine[Any, Any, ReturnT_co]]


def _run_sync_coroutine(coro: Coroutine[Any, Any, ReturnT_co]) -> ReturnT_co:
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    else:
        raise RuntimeError('zyncio functions must only await pure coroutines in sync mode')


class _ZyncFunctionWrapper(Generic[CallableT]):
    def __init__(self, func: CallableT) -> None:
        """..

        :param func: The function to wrap.
        """
        if isinstance(func, classmethod):
            func = cast(CallableT, func.__func__)
        self.func: Final[CallableT] = func
        self.__name__: str = getattr(func, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(func, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)
        if getattr(func, '__isabstractmethod__', False):
            self.__isabstractmethod__: bool = True

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'


class _BoundZyncFunctionWrapper(Generic[SelfT, CallableT]):
    def __init__(self, func: CallableT, instance: SelfT) -> None:
        """..

        :param func: The method to wrap.
        :param instance: The instance to bind the method to.
        """
        self.func: Final[CallableT] = func
        self.__self__: SelfT = instance
        self.__name__: str = getattr(func, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(func, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.func.__qualname__} of {self.__self__!r}>'


class zfunc(_ZyncFunctionWrapper[Zyncable[P, ReturnT_co]]):
    """Wrap a function to run in both sync and async modes."""

    async def run_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the function in the given mode."""
        return await self.func(zync_mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the function in sync mode."""
        return _run_sync_coroutine(self.func(SYNC, *args, **kwargs))

    async def run_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the function in async mode."""
        return await self.func(ASYNC, *args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, Coroutine[Any, Any, ReturnT_co]]:
        """Bind `run_zync` to the given mode.

        This allows syntax like ``await f[zync_mode](...)`` instead of ``await f.run_zync(zync_mode, ...)``.
        """
        return partial(self.func, zync_mode)


class _SyncProtocol(Protocol):
    __zync_mode__: Literal[Mode.SYNC]


class _AsyncProtocol(Protocol):
    __zync_mode__: Literal[Mode.ASYNC]


class _SyncProxyProtocol(Protocol):
    def __zync_proxy__(self) -> '_SyncProtocol | _SyncProxyProtocol': ...


class _AsyncProxyProtocol(Protocol):
    def __zync_proxy__(self) -> '_AsyncProtocol | _AsyncProxyProtocol': ...


class SyncMixin:
    """Mixin that makes bindable `zyncio` constructs into sync callables.

    See the documentation for each construct for details on how they interact
    with this mixin.
    """

    __zync_mode__: Literal[Mode.SYNC] = SYNC


class AsyncMixin:
    """Mixin that makes bindable `zyncio` constructs into async callables.

    See the documentation for each construct for details on how they interact
    with this mixin.
    """

    __zync_mode__: Literal[Mode.ASYNC] = ASYNC


SyncSelfT = TypeVar('SyncSelfT', bound=_SyncProtocol | _SyncProxyProtocol)
AsyncSelfT = TypeVar('AsyncSelfT', bound=_AsyncProtocol | _AsyncProxyProtocol)
SyncClassT = TypeVar('SyncClassT', bound=_SyncProtocol)
AsyncClassT = TypeVar('AsyncClassT', bound=_AsyncProtocol)


def _get_zync_mode(obj: object) -> Mode | None:
    if mode := getattr(obj, '__zync_mode__', None):
        return mode

    if (proxy_func := getattr(obj, '__zync_proxy__', None)) and callable(proxy_func):
        mode = _get_zync_mode(proxy_func())
        obj.__zync_mode__ = mode  # pyright: ignore[reportAttributeAccessIssue]
        return mode

    return None


class zmethod(_ZyncFunctionWrapper[ZyncableMethod[SelfT_co, P, ReturnT_co]]):
    """Wrap a method to run in both sync and async modes."""

    @overload
    def __get__(self, instance: None, owner: type[SelfT]) -> Self: ...
    @overload
    def __get__(self: 'zmethod[SelfT, P, ReturnT_co]', instance: SelfT, owner: type[SelfT] | None) -> 'BoundZyncMethod[SelfT, P, ReturnT_co]': ...
    def __get__(
        self: 'zmethod[SelfT, P, ReturnT_co]', instance: SelfT | None, owner: type[SelfT] | None
    ) -> 'zmethod[SelfT, P, ReturnT_co] | BoundZyncMethod[SelfT, P, ReturnT_co]':
        if instance is None:
            return self
        return BoundZyncMethod(self.func, instance)


class BoundZyncMethod(_BoundZyncFunctionWrapper[SelfT, ZyncableMethod[SelfT, P, ReturnT_co]]):
    """A bound `zyncio.zmethod`."""

    def run_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT_co]:
        """Run the method in the given mode."""
        return self.func(self.__self__, zync_mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the method in sync mode."""
        return _run_sync_coroutine(self.func(self.__self__, SYNC, *args, **kwargs))

    async def run_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the method in async mode."""
        return await self.func(self.__self__, ASYNC, *args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, Coroutine[Any, Any, ReturnT_co]]:
        """Bind `run_zync` to the given mode.

        This allows syntax like ``await f[zync_mode](...)`` instead of ``await f.run_zync(zync_mode, ...)``.
        """
        return partial(self.run_zync, zync_mode)

    @overload
    def __call__(self: 'BoundZyncMethod[SyncSelfT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> ReturnT_co: ...
    @overload
    def __call__(self: 'BoundZyncMethod[AsyncSelfT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT_co]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co | Coroutine[Any, Any, ReturnT_co]:
        match _get_zync_mode(self.__self__):
            case Mode.SYNC:
                return self.run_sync(*args, **kwargs)
            case Mode.ASYNC:
                return self.run_async(*args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable when bound to instances of SyncMixin or AsyncMixin')


class zclassmethod(_ZyncFunctionWrapper[ZyncableMethod[type[SelfT_co], P, ReturnT_co]]):
    """Wrap a method to run in both sync and async modes."""

    def __get__(
        self: 'zclassmethod[SelfT, P, ReturnT_co]', instance: SelfT | None, owner: type[SelfT]
    ) -> 'BoundZyncClassMethod[SelfT, P, ReturnT_co]':
        return BoundZyncClassMethod(self.func, owner)


class BoundZyncClassMethod(_BoundZyncFunctionWrapper[type[SelfT], ZyncableMethod[type[SelfT], P, ReturnT_co]]):
    """A bound `zyncio.zclassmethod`."""

    def __init__(self, func: ZyncableMethod[type[SelfT], P, ReturnT_co], cls: type[SelfT]) -> None:
        """..

        :param func: The method to wrap.
        :param cls: The class to bind the method to.
        """
        super().__init__(func, cls)

    def run_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT_co]:
        """Run the method in the given mode."""
        return self.func(self.__self__, zync_mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the method in sync mode."""
        return _run_sync_coroutine(self.func(self.__self__, SYNC, *args, **kwargs))

    async def run_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the method in async mode."""
        return await self.func(self.__self__, ASYNC, *args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, Coroutine[Any, Any, ReturnT_co]]:
        """Bind `run_zync` to the given mode.

        This allows syntax like ``await f[zync_mode](...)`` instead of ``await f.run_zync(zync_mode, ...)``.
        """
        return partial(self.run_zync, zync_mode)

    @overload
    def __call__(self: 'BoundZyncClassMethod[SyncClassT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> ReturnT_co: ...
    @overload
    def __call__(self: 'BoundZyncClassMethod[AsyncClassT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT_co]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co | Coroutine[Any, Any, ReturnT_co]:
        match _get_zync_mode(self.__self__):
            case Mode.SYNC:
                return self.run_sync(*args, **kwargs)
            case Mode.ASYNC:
                return self.run_async(*args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable when bound to subclasses of SyncMixin or AsyncMixin')


class zproperty(_ZyncFunctionWrapper[ZyncableMethod[SelfT_co, [], ReturnT_co]]):
    """Wrap a method to act as a property in sync mode, and as a coroutine in async mode."""

    def __init__(self, getter: ZyncableMethod[SelfT_co, [], ReturnT_co]) -> None:
        """..

        :param getter: The getter for this property.
        """
        super().__init__(getter)
        self.fget: Final[ZyncableMethod[SelfT_co, [], ReturnT_co]] = getter

    @overload
    def __get__(self: 'zproperty[SelfT, ReturnT_co]', instance: None, owner: type[SelfT]) -> 'zproperty[SelfT, ReturnT_co]': ...
    @overload
    def __get__(self: 'zproperty[SyncSelfT, ReturnT_co]', instance: SyncSelfT, owner: type[SyncSelfT] | None) -> ReturnT_co: ...
    @overload
    def __get__(
        self: 'zproperty[AsyncSelfT, ReturnT_co]', instance: AsyncSelfT, owner: type[AsyncSelfT] | None
    ) -> 'BoundZyncMethod[AsyncSelfT, [], ReturnT_co]': ...
    def __get__(
        self: 'zproperty[SelfT, ReturnT_co]', instance: SelfT | None, owner: type[SelfT] | None
    ) -> 'zproperty[SelfT, ReturnT_co] | ReturnT_co | BoundZyncMethod[SelfT, [], ReturnT_co]':
        if instance is None:
            return self

        match _get_zync_mode(instance):
            case Mode.SYNC:
                return BoundZyncMethod(self.fget, instance).run_sync()
            case Mode.ASYNC:
                return BoundZyncMethod(self.fget, instance)
            case _:
                raise TypeError(f'{type(self).__name__} can only be accessed on instances of SyncMixin or AsyncMixin')

    def setter(self, setter: ZyncableMethod[SelfT_co, [ReturnT_co], None]) -> 'ZyncSettableProperty[SelfT_co, ReturnT_co]':
        """Return a new `ZyncSettableProperty` with the given setter."""
        return ZyncSettableProperty(self.fget, setter)


class ZyncSettableProperty(zproperty[SelfT, ReturnT]):
    """A `zyncio.zproperty` with a setter."""

    def __init__(self, getter: ZyncableMethod[SelfT, [], ReturnT], setter: ZyncableMethod[SelfT, [ReturnT], None]) -> None:
        """..

        :param getter: The getter for this property.
        :param setter: The setter for this property.
        """
        super().__init__(getter)
        self.fset: Final[ZyncableMethod[SelfT, [ReturnT], None]] = setter

    @overload
    def __get__(self, instance: None, owner: type[SelfT]) -> Self: ...
    @overload
    def __get__(self: 'ZyncSettableProperty[SyncSelfT, ReturnT]', instance: SyncSelfT, owner: type[SyncSelfT] | None) -> ReturnT: ...
    @overload
    def __get__(
        self: 'ZyncSettableProperty[AsyncSelfT, ReturnT]', instance: AsyncSelfT, owner: type[AsyncSelfT] | None
    ) -> 'BoundZyncSettableProperty[AsyncSelfT, ReturnT]': ...
    def __get__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, instance: SelfT | None, owner: type[SelfT] | None
    ) -> 'ZyncSettableProperty[SelfT, ReturnT] | ReturnT | BoundZyncSettableProperty[Any, ReturnT]':
        if instance is None:
            return self

        match _get_zync_mode(instance):
            case Mode.SYNC:
                return BoundZyncMethod(self.fget, instance).run_sync()
            case Mode.ASYNC:
                return BoundZyncSettableProperty(self.fget, self.fset, instance)
            case _:
                raise TypeError(f'{type(self).__name__} can only be accessed on instances of SyncMixin or AsyncMixin')

    def __set__(self: 'ZyncSettableProperty[SyncSelfT, ReturnT]', instance: SyncSelfT, value: ReturnT) -> None:
        if not isinstance(instance, SyncMixin):
            raise TypeError(f'{type(self).__name__}.__set__ can only be used on instances of SyncMixin')
        return BoundZyncMethod(self.fset, instance).run_sync(value)


class BoundZyncSettableProperty(BoundZyncMethod[SelfT, [], ReturnT]):
    """A bound `zyncio.ZyncSettableProperty`.

    This class provides the set functionality for `ZyncSettableProperty` when
    accessed on an instance of `AsyncMixin`.
    """

    def __init__(
        self,
        getter: ZyncableMethod[SelfT, P, ReturnT],
        setter: ZyncableMethod[SelfT, [ReturnT], None],
        instance: SelfT,
    ) -> None:
        """..

        :param func: The method to wrap.
        :param instance: The instance to bind the method to.
        """
        super().__init__(getter, instance)
        self.fset: Final[ZyncableMethod[SelfT, [ReturnT], None]] = setter

    async def set(self, value: ReturnT) -> None:
        """Set the value of the property."""
        if _get_zync_mode(self.__self__) is not ASYNC:  # pragma: no cover
            raise TypeError(f'{type(self).__name__}.set can only be used on instances of AsyncMixin')
        return await BoundZyncMethod(self.fset, self.__self__).run_async(value)


ZyncableGeneratorFunc: TypeAlias = Callable[Concatenate[zyncio.Mode, P], AsyncGenerator[ReturnT_co, SendT_contra]]
ZyncableGeneratorMethod: TypeAlias = Callable[Concatenate[SelfT, zyncio.Mode, P], AsyncGenerator[ReturnT_co, SendT_contra]]


class zcontextmanager(_ZyncFunctionWrapper[ZyncableGeneratorFunc[P, ReturnT_co, None]]):
    """Similar to `contextlib.contextmanager`, but usable in both sync and async modes."""

    def __init__(self, func: ZyncableGeneratorFunc[P, ReturnT_co, None]) -> None:
        """..

        :param func: The generator function to wrap.
        """
        super().__init__(func)
        self.cm_func: Callable[Concatenate[Mode, P], AbstractAsyncContextManager[ReturnT_co]] = asynccontextmanager(func)

    @asynccontextmanager
    async def enter_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co]:
        """Enter the context manager in the given mode."""
        async with self.cm_func(zync_mode, *args, **kwargs) as val:
            yield val

    @contextmanager
    def enter_sync(self, *args: P.args, **kwargs: P.kwargs) -> Generator[ReturnT_co]:
        """Enter the context manager in sync mode."""
        cm = self.cm_func(SYNC, *args, **kwargs)
        val = _run_sync_coroutine(cm.__aenter__())
        try:
            yield val
        except BaseException:
            if not _run_sync_coroutine(cm.__aexit__(*sys.exc_info())):
                raise
        else:
            _run_sync_coroutine(cm.__aexit__(None, None, None))

    @asynccontextmanager
    async def enter_async(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co]:
        """Enter the context manager in the given mode."""
        async with self.cm_func(ASYNC, *args, **kwargs) as val:
            yield val

    def __getitem__(self, zync_mode: Mode) -> Callable[P, AbstractAsyncContextManager[ReturnT_co]]:
        """Bind `enter_zync` to the given mode.

        This allows syntax like ``async with f[zync_mode](...)`` instead of ``async with f.enter_zync(zync_mode, ...)``.
        """
        return partial(self.enter_zync, zync_mode)


class zcontextmanagermethod(_ZyncFunctionWrapper[ZyncableGeneratorMethod[SelfT_co, P, ReturnT_co, None]]):
    """Similar to `zyncio.zcontextmanager`, but binds `self` when accessed on an instance."""

    def __init__(self, func: ZyncableGeneratorMethod[SelfT_co, P, ReturnT_co, None]) -> None:
        """..

        :param func: The generator method to wrap.
        """
        super().__init__(func)

    @overload
    def __get__(self, instance: None, owner: type[SelfT]) -> Self: ...
    @overload
    def __get__(
        self: 'zcontextmanagermethod[SelfT, P, ReturnT_co]', instance: SelfT, owner: type[SelfT] | None
    ) -> 'BoundZyncContextManagerMethod[SelfT, P, ReturnT_co]': ...
    def __get__(
        self: 'zcontextmanagermethod[SelfT, P, ReturnT_co]', instance: SelfT | None, owner: type[SelfT] | None
    ) -> 'zcontextmanagermethod[SelfT, P, ReturnT_co] | BoundZyncContextManagerMethod[SelfT, P, ReturnT_co]':
        if instance is None:
            return self
        return BoundZyncContextManagerMethod(self.func, instance)


class BoundZyncContextManagerMethod(_BoundZyncFunctionWrapper[SelfT, ZyncableGeneratorMethod[SelfT, P, ReturnT_co, None]]):
    """A bound `zyncio.zcontextmanagermethod`."""

    @cached_property
    def _zync_cm(self) -> zcontextmanager[P, ReturnT_co]:
        # Use `MethodType` instead of `partial` to preserve `__name__`.
        return zcontextmanager(MethodType(self.func, self.__self__))

    def enter_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> AbstractAsyncContextManager[ReturnT_co]:
        """Enter the context manager in the given mode."""
        return self._zync_cm.enter_zync(zync_mode, *args, **kwargs)

    def enter_sync(self, *args: P.args, **kwargs: P.kwargs) -> AbstractContextManager[ReturnT_co]:
        """Enter the context manager in sync mode."""
        return self._zync_cm.enter_sync(*args, **kwargs)

    def enter_async(self, *args: P.args, **kwargs: P.kwargs) -> AbstractAsyncContextManager[ReturnT_co]:
        """Enter the context manager in async mode."""
        return self._zync_cm.enter_async(*args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, AbstractAsyncContextManager[ReturnT_co]]:
        """Bind `enter_zync` to the given mode.

        This allows syntax like ``async with f[zync_mode](...)`` instead of ``async with f.enter_zync(zync_mode, ...)``.
        """
        return self._zync_cm[zync_mode]

    @overload
    def __call__(
        self: 'BoundZyncContextManagerMethod[SyncSelfT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs
    ) -> AbstractContextManager[ReturnT_co]: ...
    @overload
    def __call__(
        self: 'BoundZyncContextManagerMethod[AsyncSelfT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs
    ) -> AbstractAsyncContextManager[ReturnT_co]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AbstractContextManager[ReturnT_co] | AbstractAsyncContextManager[ReturnT_co]:
        match _get_zync_mode(self.__self__):
            case Mode.SYNC:
                return self.enter_sync(*args, **kwargs)
            case Mode.ASYNC:
                return self.enter_async(*args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable when bound to instances of SyncMixin or AsyncMixin')


class zgenerator(_ZyncFunctionWrapper[ZyncableGeneratorFunc[P, ReturnT_co, SendT_contra]]):
    """Wrap a generator function to run in both sync and async modes."""

    def __init__(self, func: ZyncableGeneratorFunc[P, ReturnT_co, SendT_contra]) -> None:
        """..

        :param func: The generator function to wrap.
        """
        super().__init__(func)

    def run_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co, SendT_contra]:
        """Run the generator function in the given mode."""
        return self.func(zync_mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> Generator[ReturnT_co, SendT_contra]:
        """Run the generator function in sync mode."""
        async_gen = self.func(SYNC, *args, **kwargs)
        try:
            send_val = yield _run_sync_coroutine(anext(async_gen))
            while True:
                send_val = yield _run_sync_coroutine(async_gen.asend(send_val))
        except StopAsyncIteration:
            pass

    def run_async(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co, SendT_contra]:
        """Run the generator function in async mode."""
        return self.func(ASYNC, *args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, AsyncGenerator[ReturnT_co, SendT_contra]]:
        """Bind `run_zync` to the given mode.

        This allows syntax like ``async for ... in f[zync_mode](...)`` instead of
        ``async for ... in f.run_zync(zync_mode, ...)``.
        """
        return partial(self.func, zync_mode)


class zgeneratormethod(_ZyncFunctionWrapper[ZyncableGeneratorMethod[SelfT_co, P, ReturnT_co, SendT_contra]]):
    """Wrap a generator method to run in both sync and async modes."""

    def __init__(self, func: ZyncableGeneratorMethod[SelfT_co, P, ReturnT_co, SendT_contra]) -> None:
        """..

        :param func: The generator method to wrap.
        """
        super().__init__(func)

    @overload
    def __get__(self, instance: None, owner: type[SelfT]) -> Self: ...
    @overload
    def __get__(
        self: 'zgeneratormethod[SelfT, P, ReturnT_co, SendT_contra]', instance: SelfT, owner: type[SelfT] | None
    ) -> 'BoundZyncGeneratorMethod[SelfT, P, ReturnT_co, SendT_contra]': ...
    def __get__(
        self: 'zgeneratormethod[SelfT, P, ReturnT_co, SendT_contra]', instance: SelfT | None, owner: type[SelfT] | None
    ) -> 'zgeneratormethod[SelfT, P, ReturnT_co, SendT_contra] | BoundZyncGeneratorMethod[SelfT, P, ReturnT_co, SendT_contra]':
        if instance is None:
            return self
        return BoundZyncGeneratorMethod(self.func, instance)


class BoundZyncGeneratorMethod(_BoundZyncFunctionWrapper[SelfT, ZyncableGeneratorMethod[SelfT, P, ReturnT_co, SendT_contra]]):
    """A bound `zyncio.zgeneratormethod`."""

    def run_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co, SendT_contra]:
        """Run the generator function in the given mode."""
        return self.func(self.__self__, zync_mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> Generator[ReturnT_co, SendT_contra]:
        """Run the generator function in sync mode."""
        async_gen = self.func(self.__self__, SYNC, *args, **kwargs)
        try:
            send_val = yield _run_sync_coroutine(anext(async_gen))
            while True:
                send_val = yield _run_sync_coroutine(async_gen.asend(send_val))
        except StopAsyncIteration:
            pass

    def run_async(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co, SendT_contra]:
        """Run the generator function in async mode."""
        return self.func(self.__self__, ASYNC, *args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, AsyncGenerator[ReturnT_co, SendT_contra]]:
        """Bind `enter_zync` to the given mode.

        This allows syntax like ``async for ... in f[zync_mode](...)`` instead of
        ``async for ... in f.run_zync(zync_mode, ...)``.
        """
        return partial(self.run_zync, zync_mode)

    @overload
    def __call__(
        self: 'BoundZyncGeneratorMethod[SyncSelfT, P, ReturnT_co, SendT_contra]', *args: P.args, **kwargs: P.kwargs
    ) -> Generator[ReturnT_co, SendT_contra]: ...
    @overload
    def __call__(
        self: 'BoundZyncGeneratorMethod[AsyncSelfT, P, ReturnT_co, SendT_contra]', *args: P.args, **kwargs: P.kwargs
    ) -> AsyncGenerator[ReturnT_co, SendT_contra]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Generator[ReturnT_co, SendT_contra] | AsyncGenerator[ReturnT_co, SendT_contra]:
        match _get_zync_mode(self.__self__):
            case Mode.SYNC:
                return self.run_sync(*args, **kwargs)
            case Mode.ASYNC:
                return self.run_async(*args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable when bound to instances of SyncMixin or AsyncMixin')
