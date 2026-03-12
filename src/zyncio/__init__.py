"""Write dual sync/async interfaces with minimal duplication."""

from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from enum import Enum
from functools import partial
import sys
from types import MethodType
from typing import Any, Concatenate, Final, Generic, ParamSpec, TypeAlias, TypeVar, overload
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


P = ParamSpec('P')
ReturnT = TypeVar('ReturnT')
SelfT = TypeVar('SelfT')


Zyncable = Callable[Concatenate[Mode, P], Coroutine[Any, Any, ReturnT]]
ZyncableMethod = Callable[Concatenate[SelfT, Mode, P], Coroutine[Any, Any, ReturnT]]


def _run_sync_coroutine(coro: Coroutine[Any, Any, ReturnT]) -> ReturnT:
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    else:
        raise RuntimeError('zyncio functions must only await pure coroutines in sync mode')


class zfunc(Generic[P, ReturnT]):
    """Wrap a function to run in both sync and async modes."""

    def __init__(self, func: Zyncable[P, ReturnT]) -> None:
        """..

        :param func: The function to wrap.
        """
        self.func: Final[Zyncable[P, ReturnT]] = func
        self.__name__: str = getattr(func, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(func, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the function in sync mode."""
        return _run_sync_coroutine(self.func(SYNC, *args, **kwargs))

    async def run_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the function in async mode."""
        return await self.func(ASYNC, *args, **kwargs)


class SyncMixin:
    """Mixin that makes bindable `zyncio` constructs into sync callables.

    See the documentation for each construct for details on how they interact
    with this mixin.
    """


class AsyncMixin:
    """Mixin that makes bindable `zyncio` constructs into async callables.

    See the documentation for each construct for details on how they interact
    with this mixin.
    """


SyncSelfT = TypeVar('SyncSelfT', bound=SyncMixin)
AsyncSelfT = TypeVar('AsyncSelfT', bound=AsyncMixin)


class zmethod(Generic[SelfT, P, ReturnT]):
    """Wrap a method to run in both sync and async modes."""

    def __init__(self, func: ZyncableMethod[SelfT, P, ReturnT]) -> None:
        """..

        :param func: The method to wrap.
        """
        self.func: Final[ZyncableMethod[SelfT, P, ReturnT]] = func
        self.__name__: str = getattr(func, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(func, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'

    @overload
    def __get__(self, instance: None, owner: type[SelfT]) -> Self: ...
    @overload
    def __get__(self, instance: SelfT, owner: type[SelfT] | None) -> 'BoundZyncMethod[SelfT, P, ReturnT]': ...
    def __get__(self, instance: SelfT | None, owner: type[SelfT] | None) -> 'Self | BoundZyncMethod[SelfT, P, ReturnT]':
        if instance is None:
            return self
        return BoundZyncMethod(self.func, instance)


class zclassmethod(Generic[SelfT, P, ReturnT]):
    """Wrap a method to run in both sync and async modes."""

    def __init__(self, func: ZyncableMethod[type[SelfT], P, ReturnT]) -> None:
        """..

        :param func: The method to wrap.
        """
        self.func: Final[ZyncableMethod[type[SelfT], P, ReturnT]] = func.__func__ if isinstance(func, classmethod) else func
        self.__name__: str = getattr(func, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(func, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'

    def __get__(self, instance: SelfT | None, owner: type[SelfT]) -> 'BoundZyncClassMethod[SelfT, P, ReturnT]':
        return BoundZyncClassMethod(self.func, owner)


class BoundZyncMethod(Generic[SelfT, P, ReturnT]):
    """A bound `zyncio.zmethod`."""

    def __init__(self, func: ZyncableMethod[SelfT, P, ReturnT], instance: SelfT) -> None:
        """..

        :param func: The method to wrap.
        :param instance: The instance to bind the method to.
        """
        self.func: Final[ZyncableMethod[SelfT, P, ReturnT]] = func
        self.instance: Final[SelfT] = instance

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.func.__qualname__} of {self.instance!r}>'

    def run_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT]:
        """Run the method in the given mode."""
        return self.func(self.instance, zync_mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the method in sync mode."""
        return _run_sync_coroutine(self.func(self.instance, SYNC, *args, **kwargs))

    async def run_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the method in async mode."""
        return await self.func(self.instance, ASYNC, *args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, Coroutine[Any, Any, ReturnT]]:
        """Bind `run_zync` to the given mode.

        This allows syntax like ``await f[zync_mode](...)`` instead of ``await f.run_zync(zync_mode, ...)``.
        """
        return partial(self.run_zync, zync_mode)

    @overload
    def __call__(self: 'BoundZyncMethod[SyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs) -> ReturnT: ...
    @overload
    def __call__(self: 'BoundZyncMethod[AsyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT | Coroutine[Any, Any, ReturnT]:
        if isinstance(self.instance, SyncMixin):
            return self.run_sync(*args, **kwargs)
        elif isinstance(self.instance, AsyncMixin):
            return self.run_async(*args, **kwargs)
        else:
            raise TypeError(f'{type(self).__name__} is only callable when bound to instances of SyncMixin or AsyncMixin')


class BoundZyncClassMethod(Generic[SelfT, P, ReturnT]):
    """A bound `zyncio.zclassmethod`."""

    def __init__(self, func: ZyncableMethod[type[SelfT], P, ReturnT], cls: type[SelfT]) -> None:
        """..

        :param func: The method to wrap.
        :param cls: The class to bind the method to.
        """
        self.func: Final[ZyncableMethod[type[SelfT], P, ReturnT]] = func
        self.cls: Final[type[SelfT]] = cls

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.func.__qualname__} of {self.cls!r}>'

    def run_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT]:
        """Run the method in the given mode."""
        return self.func(self.cls, zync_mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the method in sync mode."""
        return _run_sync_coroutine(self.func(self.cls, SYNC, *args, **kwargs))

    async def run_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the method in async mode."""
        return await self.func(self.cls, ASYNC, *args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, Coroutine[Any, Any, ReturnT]]:
        """Bind `run_zync` to the given mode.

        This allows syntax like ``await f[zync_mode](...)`` instead of ``await f.run_zync(zync_mode, ...)``.
        """
        return partial(self.run_zync, zync_mode)

    @overload
    def __call__(self: 'BoundZyncClassMethod[SyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs) -> ReturnT: ...
    @overload
    def __call__(self: 'BoundZyncClassMethod[AsyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT | Coroutine[Any, Any, ReturnT]:
        if issubclass(self.cls, SyncMixin):
            return self.run_sync(*args, **kwargs)
        elif issubclass(self.cls, AsyncMixin):
            return self.run_async(*args, **kwargs)
        else:
            raise TypeError(f'{type(self).__name__} is only callable when bound to subclasses of SyncMixin or AsyncMixin')


class zproperty(Generic[SelfT, ReturnT]):
    """Wrap a method to act as a property in sync mode, and as a coroutine in async mode."""

    def __init__(self, getter: ZyncableMethod[SelfT, [], ReturnT]) -> None:
        """..

        :param getter: The getter for this property.
        """
        self.fget: Final[ZyncableMethod[SelfT, [], ReturnT]] = getter
        self.__name__: str = getattr(getter, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(getter, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(getter, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'

    @overload
    def __get__(self, instance: None, owner: type[SelfT]) -> Self: ...
    @overload
    def __get__(self: 'zproperty[SyncSelfT, ReturnT]', instance: SyncSelfT, owner: type[SyncSelfT] | None) -> ReturnT: ...
    @overload
    def __get__(
        self: 'zproperty[AsyncSelfT, ReturnT]', instance: AsyncSelfT, owner: type[AsyncSelfT] | None
    ) -> 'BoundZyncMethod[SelfT, [], ReturnT]': ...
    def __get__(self, instance: SelfT | None, owner: type[SelfT] | None) -> 'Self | ReturnT | BoundZyncMethod[SelfT, [], ReturnT]':
        if instance is None:
            return self
        elif isinstance(instance, SyncMixin):
            return BoundZyncMethod(self.fget, instance).run_sync()
        elif isinstance(instance, AsyncMixin):
            return BoundZyncMethod(self.fget, instance)
        raise TypeError(f'{type(self).__name__} can only be accessed on instances of SyncMixin or AsyncMixin')

    def setter(self, setter: ZyncableMethod[SelfT, [ReturnT], None]) -> 'ZyncSettableProperty[SelfT, ReturnT]':
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
    def __get__(self: 'zproperty[SyncSelfT, ReturnT]', instance: SyncSelfT, owner: type[SyncSelfT] | None) -> ReturnT: ...
    @overload
    def __get__(
        self: 'zproperty[AsyncSelfT, ReturnT]', instance: AsyncSelfT, owner: type[AsyncSelfT] | None
    ) -> 'BoundZyncSettableProperty[SelfT, ReturnT]': ...
    def __get__(self, instance: SelfT | None, owner: type[SelfT] | None) -> 'Self | ReturnT | BoundZyncSettableProperty[SelfT, ReturnT]':
        if instance is None:
            return self
        elif isinstance(instance, SyncMixin):
            return BoundZyncMethod(self.fget, instance).run_sync()
        elif isinstance(instance, AsyncMixin):
            return BoundZyncSettableProperty(self.fget, self.fset, instance)
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

    async def set(self: 'BoundZyncSettableProperty[AsyncSelfT, ReturnT]', value: ReturnT) -> None:
        """Set the value of the property."""
        if not isinstance(self.instance, AsyncMixin):  # pragma: no cover
            raise TypeError(f'{type(self).__name__}.set can only be used on instances of AsyncMixin')
        return await BoundZyncMethod(self.fset, self.instance).run_async(value)


ZyncableGeneratorFunc: TypeAlias = Callable[Concatenate[zyncio.Mode, P], AsyncGenerator[ReturnT]]
ZyncableGeneratorMethod: TypeAlias = Callable[Concatenate[SelfT, zyncio.Mode, P], AsyncGenerator[ReturnT]]


class zcontextmanager(Generic[P, ReturnT]):
    """Similar to `contextlib.contextmanager`, but usable in both sync and async modes."""

    def __init__(self, func: ZyncableGeneratorFunc[P, ReturnT]) -> None:
        """..

        :param func: The generator function to wrap.
        """
        self.cm_func: Callable[Concatenate[Mode, P], AbstractAsyncContextManager[ReturnT]] = asynccontextmanager(func)
        self.__name__: str = getattr(func, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(func, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'

    @asynccontextmanager
    async def enter_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT]:
        """Enter the context manager in the given mode."""
        async with self.cm_func(zync_mode, *args, **kwargs) as val:
            yield val

    @contextmanager
    def enter_sync(self, *args: P.args, **kwargs: P.kwargs) -> Generator[ReturnT]:
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
    async def enter_async(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT]:
        """Enter the context manager in the given mode."""
        async with self.cm_func(ASYNC, *args, **kwargs) as val:
            yield val

    def __getitem__(self, zync_mode: Mode) -> Callable[P, AbstractAsyncContextManager[ReturnT]]:
        """Bind `enter_zync` to the given mode.

        This allows syntax like ``async with f[zync_mode](...)`` instead of ``async with f.enter_zync(zync_mode, ...)``.
        """
        return partial(self.enter_zync, zync_mode)


class zcontextmanagermethod(Generic[SelfT, P, ReturnT]):
    """Similar to `zyncio.zcontextmanager`, but binds `self` when accessed on an instance."""

    def __init__(self, func: ZyncableGeneratorMethod[SelfT, P, ReturnT]) -> None:
        """..

        :param func: The generator method to wrap.
        """
        self.func: Callable[Concatenate[SelfT, Mode, P], AsyncGenerator[ReturnT, None]] = func
        self.__name__: str = getattr(func, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(func, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'

    @overload
    def __get__(self, instance: None, owner: type[SelfT]) -> Self: ...
    @overload
    def __get__(self, instance: SelfT, owner: type[SelfT] | None) -> 'BoundZyncContextManagerMethod[SelfT, P, ReturnT]': ...
    def __get__(self, instance: SelfT | None, owner: type[SelfT] | None) -> 'Self | BoundZyncContextManagerMethod[SelfT, P, ReturnT]':
        if instance is None:
            return self
        return BoundZyncContextManagerMethod(self.func, instance)


class BoundZyncContextManagerMethod(Generic[SelfT, P, ReturnT]):
    """A bound `zyncio.zcontextmanagermethod`."""

    def __init__(self, func: ZyncableGeneratorMethod[SelfT, P, ReturnT], instance: SelfT) -> None:
        """..

        :param func: The generator method to wrap.
        :param instance: The instance to bind the method to.
        """
        # Use `MethodType` instead of `partial` to preserve `__name__`.
        self.zync_cm: Final[zcontextmanager[P, ReturnT]] = zcontextmanager(MethodType(func, instance))
        self.instance: Final[SelfT] = instance

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.zync_cm.__qualname__} of {self.instance!r}>'

    def enter_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> AbstractAsyncContextManager[ReturnT]:
        """Enter the context manager in the given mode."""
        return self.zync_cm.enter_zync(zync_mode, *args, **kwargs)

    def enter_sync(self, *args: P.args, **kwargs: P.kwargs) -> AbstractContextManager[ReturnT]:
        """Enter the context manager in sync mode."""
        return self.zync_cm.enter_sync(*args, **kwargs)

    def enter_async(self, *args: P.args, **kwargs: P.kwargs) -> AbstractAsyncContextManager[ReturnT]:
        """Enter the context manager in async mode."""
        return self.zync_cm.enter_async(*args, **kwargs)

    def __getitem__(self, zync_mode: Mode) -> Callable[P, AbstractAsyncContextManager[ReturnT]]:
        """Bind `enter_zync` to the given mode.

        This allows syntax like ``async with f[zync_mode](...)`` instead of ``async with f.enter_zync(zync_mode, ...)``.
        """
        return partial(self.enter_zync, zync_mode)

    @overload
    def __call__(
        self: 'BoundZyncContextManagerMethod[SyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs
    ) -> AbstractContextManager[ReturnT]: ...
    @overload
    def __call__(
        self: 'BoundZyncContextManagerMethod[AsyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs
    ) -> AbstractAsyncContextManager[ReturnT]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AbstractContextManager[ReturnT] | AbstractAsyncContextManager[ReturnT]:
        if isinstance(self.instance, SyncMixin):
            return self.enter_sync(*args, **kwargs)
        elif isinstance(self.instance, AsyncMixin):
            return self.enter_async(*args, **kwargs)
        else:
            raise TypeError(f'{type(self).__name__} is only callable when bound to instances of SyncMixin or AsyncMixin')
