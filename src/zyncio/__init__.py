"""Write dual sync/async interfaces with minimal duplication."""

from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from enum import Enum
from functools import cached_property, partial
import sys
from typing import Any, Concatenate, Final, Generic, Literal, ParamSpec, Protocol, TypeAlias, TypeVar, cast, overload
from typing_extensions import Self


__all__ = [
    'Mode',
    'SYNC',
    'ASYNC',
    'ZyncModeT_co',
    'zfunc',
    'zmethod',
    'zclassmethod',
    'zproperty',
    'zcontextmanager',
    'zcontextmanagermethod',
    'zgenerator',
    'zgeneratormethod',
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

ZyncModeT_co = TypeVar('ZyncModeT_co', bound=Mode, covariant=True)
"""Convenience `TypeVar` for writing ZyncIO ABCs."""


_REQUIRED_INTERFACE_MESSAGE = 'subclass zyncio.SyncMixin or zyncio.AsyncMixin, or define the __zync_proxy__() method to return one that does.'


class _ZyncModeDescriptor(Generic[ZyncModeT_co]):
    """This descriptor allows us to define immutable (and therefore covariant) class constants.

    If PEP 767 is accepted, this can hopefully be replaced with a simple `ReadOnly[ClassVar[...]]`.
    """

    def __init__(self, mode: ZyncModeT_co = cast(Mode, ...)) -> None:
        self.mode: ZyncModeT_co = mode

    def __get__(self, instance: object, owner: type | None) -> ZyncModeT_co:
        if not isinstance(self.mode, Mode):
            raise AttributeError(f'__zync_mode__ is only accessible on classes or objects that {_REQUIRED_INTERFACE_MESSAGE}')
        return self.mode


class _ZyncProtocol(Protocol):
    __zync_mode__ = _ZyncModeDescriptor()


class _SyncProtocol(Protocol):
    __zync_mode__: _ZyncModeDescriptor[Literal[Mode.SYNC]] = _ZyncModeDescriptor(Mode.SYNC)


class _AsyncProtocol(Protocol):
    __zync_mode__: _ZyncModeDescriptor[Literal[Mode.ASYNC]] = _ZyncModeDescriptor(Mode.ASYNC)


class _ZyncProxyProtocol(Protocol):
    def __zync_proxy__(self) -> '_ZyncProtocol | _ZyncProxyProtocol': ...


class _SyncProxyProtocol(Protocol):
    def __zync_proxy__(self) -> '_SyncProtocol | _SyncProxyProtocol': ...


class _AsyncProxyProtocol(Protocol):
    def __zync_proxy__(self) -> '_AsyncProtocol | _AsyncProxyProtocol': ...


class ZyncBase:
    __zync_mode__: _ZyncModeDescriptor[Mode] = _ZyncModeDescriptor()


def _check_mixin_mro(cls: type, mixin_class: type) -> None:
    for parent in cls.mro():
        if parent is mixin_class:
            # Stop once we find the mixin class, only earlier classes are
            # potentially problematic.
            break

        if '__zync_mode__' in parent.__dict__:
            # Try to find the specific direct base class that inherits from the
            # problematic parent.
            found_mixin_class = False
            for base in cls.__bases__[::-1]:
                # Skip base classes that come after the mixin
                if not found_mixin_class:
                    found_mixin_class = base is mixin_class
                    continue

                if parent in base.mro():
                    parent = base
                    break
            else:  # pragma: no cover
                pass

            raise TypeError(
                f'{mixin_class.__name__}: __zync_mode__ shadowed by definition in parent {parent.__name__}. '
                f'{mixin_class.__name__} should come first in the inheritance list.'
            )
    else:  # pragma: no cover
        pass


class SyncMixin:
    """Mixin that makes bindable `zyncio` constructs into sync callables.

    See the documentation for each construct for details on how they interact
    with this mixin.
    """

    __zync_mode__: _ZyncModeDescriptor[Literal[Mode.SYNC]] = _ZyncModeDescriptor(Mode.SYNC)

    def __init_subclass__(cls) -> None:
        _check_mixin_mro(cls, __class__)


class AsyncMixin:
    """Mixin that makes bindable `zyncio` constructs into async callables.

    See the documentation for each construct for details on how they interact
    with this mixin.
    """

    __zync_mode__: _ZyncModeDescriptor[Literal[Mode.ASYNC]] = _ZyncModeDescriptor(Mode.ASYNC)

    def __init_subclass__(cls) -> None:
        _check_mixin_mro(cls, __class__)


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

ZyncSelfT = TypeVar('ZyncSelfT', bound=_ZyncProtocol | _ZyncProxyProtocol)
ZyncSelfT_co = TypeVar('ZyncSelfT_co', bound=_ZyncProtocol | _ZyncProxyProtocol, covariant=True)
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

    return None  # pragma: no cover


Zyncable = Callable[Concatenate[Mode, P], Coroutine[Any, Any, ReturnT_co]]
ZyncableMethod = Callable[Concatenate[ZyncSelfT_co, P], Coroutine[Any, Any, ReturnT_co]]


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


class _BoundZyncFunctionWrapper(Generic[ZyncSelfT_co, CallableT]):
    def __init__(self, func: CallableT, instance: ZyncSelfT_co) -> None:
        """..

        :param func: The method to wrap.
        :param instance: The instance to bind the method to.
        """
        self.func: Final[CallableT] = func
        self.__self__: ZyncSelfT_co = instance
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


class zmethod(_ZyncFunctionWrapper[ZyncableMethod[ZyncSelfT_co, P, ReturnT_co]]):
    """Wrap a method to run in both sync and async modes."""

    @overload
    def __get__(self, instance: None, owner: type[ZyncSelfT]) -> Self: ...
    @overload
    def __get__(
        self: 'zmethod[ZyncSelfT, P, ReturnT_co]', instance: ZyncSelfT, owner: type[ZyncSelfT] | None
    ) -> 'BoundZyncMethod[ZyncSelfT, P, ReturnT_co]': ...
    def __get__(
        self: 'zmethod[ZyncSelfT, P, ReturnT_co]', instance: ZyncSelfT | None, owner: type[ZyncSelfT] | None
    ) -> 'zmethod[ZyncSelfT, P, ReturnT_co] | BoundZyncMethod[ZyncSelfT, P, ReturnT_co]':
        if instance is None:
            return self
        return BoundZyncMethod(self.func, instance)


class BoundZyncMethod(_BoundZyncFunctionWrapper[ZyncSelfT_co, ZyncableMethod[ZyncSelfT_co, P, ReturnT_co]]):
    """A bound `zyncio.zmethod`."""

    async def zync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the method as a coroutine regardless of mode."""
        return await self.func(self.__self__, *args, **kwargs)

    @overload
    def __call__(self: 'BoundZyncMethod[SyncSelfT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> ReturnT_co: ...
    @overload
    def __call__(self: 'BoundZyncMethod[AsyncSelfT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT_co]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co | Coroutine[Any, Any, ReturnT_co]:
        match _get_zync_mode(self.__self__):
            case Mode.SYNC:
                return _run_sync_coroutine(self.func(self.__self__, *args, **kwargs))
            case Mode.ASYNC:
                return self.func(self.__self__, *args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable on objects that {_REQUIRED_INTERFACE_MESSAGE}')


class zclassmethod(_ZyncFunctionWrapper[ZyncableMethod[type[ZyncSelfT_co], P, ReturnT_co]]):
    """Wrap a method to run in both sync and async modes."""

    def __get__(
        self: 'zclassmethod[ZyncSelfT, P, ReturnT_co]', instance: ZyncSelfT | None, owner: type[ZyncSelfT]
    ) -> 'BoundZyncClassMethod[ZyncSelfT, P, ReturnT_co]':
        return BoundZyncClassMethod(self.func, owner)


class BoundZyncClassMethod(_BoundZyncFunctionWrapper[type[ZyncSelfT], ZyncableMethod[type[ZyncSelfT], P, ReturnT_co]]):
    """A bound `zyncio.zclassmethod`."""

    def __init__(self, func: ZyncableMethod[type[ZyncSelfT], P, ReturnT_co], cls: type[ZyncSelfT]) -> None:
        """..

        :param func: The method to wrap.
        :param cls: The class to bind the method to.
        """
        super().__init__(func, cls)

    async def zync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the method as a coroutine regardless of mode."""
        return await self.func(self.__self__, *args, **kwargs)

    @overload
    def __call__(self: 'BoundZyncClassMethod[SyncClassT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> ReturnT_co: ...
    @overload
    def __call__(self: 'BoundZyncClassMethod[AsyncClassT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT_co]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co | Coroutine[Any, Any, ReturnT_co]:
        match _get_zync_mode(self.__self__):
            case Mode.SYNC:
                return _run_sync_coroutine(self.func(self.__self__, *args, **kwargs))
            case Mode.ASYNC:
                return self.func(self.__self__, *args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable on classes that subclass zyncio.SyncMixin or zyncio.AsyncMixin')


class zproperty(_ZyncFunctionWrapper[ZyncableMethod[ZyncSelfT_co, [], ReturnT_co]]):
    """Wrap a method to act as a property in sync mode, and as a coroutine in async mode."""

    def __init__(self, getter: ZyncableMethod[ZyncSelfT_co, [], ReturnT_co]) -> None:
        """..

        :param getter: The getter for this property.
        """
        super().__init__(getter)
        self.fget: Final[ZyncableMethod[ZyncSelfT_co, [], ReturnT_co]] = getter

    @overload
    def __get__(self: 'zproperty[ZyncSelfT, ReturnT_co]', instance: None, owner: type[ZyncSelfT]) -> 'zproperty[ZyncSelfT, ReturnT_co]': ...
    @overload
    def __get__(self: 'zproperty[SyncSelfT, ReturnT_co]', instance: SyncSelfT, owner: type[SyncSelfT] | None) -> ReturnT_co: ...
    @overload
    def __get__(
        self: 'zproperty[AsyncSelfT, ReturnT_co]', instance: AsyncSelfT, owner: type[AsyncSelfT] | None
    ) -> 'BoundZyncMethod[AsyncSelfT, [], ReturnT_co]': ...
    def __get__(
        self: 'zproperty[ZyncSelfT, ReturnT_co]', instance: ZyncSelfT | None, owner: type[ZyncSelfT] | None
    ) -> 'zproperty[ZyncSelfT, ReturnT_co] | ReturnT_co | BoundZyncMethod[ZyncSelfT, [], ReturnT_co]':
        if instance is None:
            return self

        match _get_zync_mode(instance):
            case Mode.SYNC:
                return _run_sync_coroutine(self.fget(instance))
            case Mode.ASYNC:
                return BoundZyncMethod(self.fget, instance)
            case _:
                raise TypeError(f'{type(self).__name__} is only accessible on objects that {_REQUIRED_INTERFACE_MESSAGE}')

    async def __call__(self: 'zproperty[ZyncSelfT, ReturnT_co]', instance: ZyncSelfT) -> ReturnT_co:
        """Call this `zproperty`'s getter with the given instance."""
        return await self.fget(instance)

    def setter(self, setter: ZyncableMethod[ZyncSelfT_co, [ReturnT_co], None]) -> 'ZyncSettableProperty[ZyncSelfT_co, ReturnT_co]':
        """Return a new `ZyncSettableProperty` with the given setter."""
        return ZyncSettableProperty(self.fget, setter)


class ZyncSettableProperty(zproperty[ZyncSelfT, ReturnT]):
    """A `zyncio.zproperty` with a setter."""

    def __init__(self, getter: ZyncableMethod[ZyncSelfT, [], ReturnT], setter: ZyncableMethod[ZyncSelfT, [ReturnT], None]) -> None:
        """..

        :param getter: The getter for this property.
        :param setter: The setter for this property.
        """
        super().__init__(getter)
        self.fset: Final[ZyncableMethod[ZyncSelfT, [ReturnT], None]] = setter

    @overload
    def __get__(self, instance: None, owner: type[ZyncSelfT]) -> Self: ...
    @overload
    def __get__(self: 'ZyncSettableProperty[SyncSelfT, ReturnT]', instance: SyncSelfT, owner: type[SyncSelfT] | None) -> ReturnT: ...
    @overload
    def __get__(
        self: 'ZyncSettableProperty[AsyncSelfT, ReturnT]', instance: AsyncSelfT, owner: type[AsyncSelfT] | None
    ) -> 'BoundZyncSettableProperty[AsyncSelfT, ReturnT]': ...
    def __get__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, instance: ZyncSelfT | None, owner: type[ZyncSelfT] | None
    ) -> 'ZyncSettableProperty[ZyncSelfT, ReturnT] | ReturnT | BoundZyncSettableProperty[Any, ReturnT]':
        if instance is None:
            return self

        match _get_zync_mode(instance):
            case Mode.SYNC:
                return _run_sync_coroutine(self.fget(instance))
            case Mode.ASYNC:
                return BoundZyncSettableProperty(self.fget, self.fset, instance)
            case _:
                raise TypeError(f'{type(self).__name__} is only accessible on objects that {_REQUIRED_INTERFACE_MESSAGE}')

    def __set__(self: 'ZyncSettableProperty[SyncSelfT, ReturnT]', instance: SyncSelfT, value: ReturnT) -> None:
        match _get_zync_mode(instance):
            case Mode.SYNC:
                return _run_sync_coroutine(self.fset(instance, value))
            case Mode.ASYNC:
                raise TypeError(f'{type(self).__name__}.__set__ does not support async mode')
            case _:  # pragma: no cover
                raise TypeError(f'{type(self).__name__} is only settable on objects that {_REQUIRED_INTERFACE_MESSAGE}')


class BoundZyncSettableProperty(BoundZyncMethod[ZyncSelfT, [], ReturnT]):
    """A bound `zyncio.ZyncSettableProperty`.

    This class provides the set functionality for `ZyncSettableProperty` when
    accessed on an async-mode object.
    """

    def __init__(
        self,
        getter: ZyncableMethod[ZyncSelfT, P, ReturnT],
        setter: ZyncableMethod[ZyncSelfT, [ReturnT], None],
        instance: ZyncSelfT,
    ) -> None:
        """..

        :param func: The method to wrap.
        :param instance: The instance to bind the method to.
        """
        super().__init__(getter, instance)
        self.fset: Final[ZyncableMethod[ZyncSelfT, [ReturnT], None]] = setter

    async def set(self, value: ReturnT) -> None:
        """Set the value of the property."""
        match _get_zync_mode(self.__self__):
            case Mode.SYNC:  # pragma: no cover
                raise TypeError(f'{type(self).__name__}.set does not support sync mode')
            case Mode.ASYNC:
                return await self.fset(self.__self__, value)
            case _:  # pragma: no cover
                raise TypeError(f'{type(self).__name__} is only settable on objects that {_REQUIRED_INTERFACE_MESSAGE}')


ZyncableGeneratorFunc: TypeAlias = Callable[Concatenate[Mode, P], AsyncGenerator[ReturnT_co, SendT_contra]]
ZyncableGeneratorMethod: TypeAlias = Callable[Concatenate[ZyncSelfT, P], AsyncGenerator[ReturnT_co, SendT_contra]]


@contextmanager
def _async_context_manager_to_sync(cm: AbstractAsyncContextManager[ReturnT_co]) -> Generator[ReturnT_co]:
    val = _run_sync_coroutine(cm.__aenter__())
    try:
        yield val
    except BaseException:
        if not _run_sync_coroutine(cm.__aexit__(*sys.exc_info())):
            raise
    else:
        _run_sync_coroutine(cm.__aexit__(None, None, None))


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

    def enter_sync(self, *args: P.args, **kwargs: P.kwargs) -> AbstractContextManager[ReturnT_co]:
        """Enter the context manager in sync mode."""
        return _async_context_manager_to_sync(self.cm_func(SYNC, *args, **kwargs))

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


class zcontextmanagermethod(_ZyncFunctionWrapper[ZyncableGeneratorMethod[ZyncSelfT_co, P, ReturnT_co, None]]):
    """Similar to `zyncio.zcontextmanager`, but binds `self` when accessed on an instance."""

    def __init__(self, func: ZyncableGeneratorMethod[ZyncSelfT_co, P, ReturnT_co, None]) -> None:
        """..

        :param func: The generator method to wrap.
        """
        super().__init__(func)

    @overload
    def __get__(self, instance: None, owner: type[ZyncSelfT]) -> Self: ...
    @overload
    def __get__(
        self: 'zcontextmanagermethod[ZyncSelfT, P, ReturnT_co]', instance: ZyncSelfT, owner: type[ZyncSelfT] | None
    ) -> 'BoundZyncContextManagerMethod[ZyncSelfT, P, ReturnT_co]': ...
    def __get__(
        self: 'zcontextmanagermethod[ZyncSelfT, P, ReturnT_co]', instance: ZyncSelfT | None, owner: type[ZyncSelfT] | None
    ) -> 'zcontextmanagermethod[ZyncSelfT, P, ReturnT_co] | BoundZyncContextManagerMethod[ZyncSelfT, P, ReturnT_co]':
        if instance is None:
            return self
        return BoundZyncContextManagerMethod(self.func, instance)


class BoundZyncContextManagerMethod(_BoundZyncFunctionWrapper[ZyncSelfT, ZyncableGeneratorMethod[ZyncSelfT, P, ReturnT_co, None]]):
    """A bound `zyncio.zcontextmanagermethod`."""

    @cached_property
    def _cm(self) -> Callable[Concatenate[ZyncSelfT, P], AbstractAsyncContextManager[ReturnT_co]]:
        return asynccontextmanager(self.func)

    def zync(self, *args: P.args, **kwargs: P.kwargs) -> AbstractAsyncContextManager[ReturnT_co]:
        """Enter the context manager as an async context manager regardless of mode."""
        return self._cm(self.__self__, *args, **kwargs)

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
                return _async_context_manager_to_sync(self._cm(self.__self__, *args, **kwargs))
            case Mode.ASYNC:
                return self._cm(self.__self__, *args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable on objects that {_REQUIRED_INTERFACE_MESSAGE}')


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


class zgeneratormethod(_ZyncFunctionWrapper[ZyncableGeneratorMethod[ZyncSelfT_co, P, ReturnT_co, SendT_contra]]):
    """Wrap a generator method to run in both sync and async modes."""

    def __init__(self, func: ZyncableGeneratorMethod[ZyncSelfT_co, P, ReturnT_co, SendT_contra]) -> None:
        """..

        :param func: The generator method to wrap.
        """
        super().__init__(func)

    @overload
    def __get__(self, instance: None, owner: type[ZyncSelfT]) -> Self: ...
    @overload
    def __get__(
        self: 'zgeneratormethod[ZyncSelfT, P, ReturnT_co, SendT_contra]', instance: ZyncSelfT, owner: type[ZyncSelfT] | None
    ) -> 'BoundZyncGeneratorMethod[ZyncSelfT, P, ReturnT_co, SendT_contra]': ...
    def __get__(
        self: 'zgeneratormethod[ZyncSelfT, P, ReturnT_co, SendT_contra]', instance: ZyncSelfT | None, owner: type[ZyncSelfT] | None
    ) -> 'zgeneratormethod[ZyncSelfT, P, ReturnT_co, SendT_contra] | BoundZyncGeneratorMethod[ZyncSelfT, P, ReturnT_co, SendT_contra]':
        if instance is None:
            return self
        return BoundZyncGeneratorMethod(self.func, instance)


class BoundZyncGeneratorMethod(_BoundZyncFunctionWrapper[ZyncSelfT, ZyncableGeneratorMethod[ZyncSelfT, P, ReturnT_co, SendT_contra]]):
    """A bound `zyncio.zgeneratormethod`."""

    def zync(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co, SendT_contra]:
        """Run the generator function in the given mode."""
        return self.func(self.__self__, *args, **kwargs)

    def _run_sync(self, *args: P.args, **kwargs: P.kwargs) -> Generator[ReturnT_co, SendT_contra]:
        """Run the generator function as an async generator regardless of mode."""
        async_gen = self.func(self.__self__, *args, **kwargs)
        try:
            send_val = yield _run_sync_coroutine(anext(async_gen))
            while True:
                send_val = yield _run_sync_coroutine(async_gen.asend(send_val))
        except StopAsyncIteration:
            pass

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
                return self._run_sync(*args, **kwargs)
            case Mode.ASYNC:
                return self.func(self.__self__, *args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable on objects that {_REQUIRED_INTERFACE_MESSAGE}')
