"""Write dual sync/async interfaces with minimal duplication."""

from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any, Concatenate, Final, Generic, ParamSpec, TypeVar, overload
from typing_extensions import Self


__all__ = [
    'Mode',
    'SYNC',
    'ASYNC',
    'zfunc',
    'zmethod',
    'zclassmethod',
    'zproperty',
    'SyncMixin',
    'AsyncMixin',
]


class Mode(Enum):
    """`zync` execution mode."""

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
        raise RuntimeError('zync functions must only await pure coroutines in sync mode')


class zfunc(Generic[P, ReturnT]):
    """Wrap a function to run in both sync and async modes."""

    def __init__(self, func: Zyncable[P, ReturnT]) -> None:
        """..

        :param func: The function to wrap.
        """
        self.func: Final[Zyncable[P, ReturnT]] = func
        self.__name__: str = func.__name__
        self.__qualname__: str = getattr(func, '__qualname__', func.__name__)
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
    """Mixin that makes `zync.zmethod`s into sync callables."""


class AsyncMixin:
    """Mixin that makes `zync.zmethod`s into async callables."""


class zmethod(Generic[SelfT, P, ReturnT]):
    """Wrap a method to run in both sync and async modes."""

    def __init__(self, func: ZyncableMethod[SelfT, P, ReturnT]) -> None:
        """..

        :param func: The method to wrap.
        """
        self.func: Final[ZyncableMethod[SelfT, P, ReturnT]] = func
        self.__name__: str = func.__name__
        self.__qualname__: str = getattr(func, '__qualname__', func.__name__)
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
        self.__name__: str = func.__name__
        self.__qualname__: str = getattr(func, '__qualname__', func.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'

    def __get__(self, instance: SelfT | None, owner: type[SelfT]) -> 'BoundZyncClassMethod[SelfT, P, ReturnT]':
        return BoundZyncClassMethod(self.func, owner)


SyncSelfT = TypeVar('SyncSelfT', bound=SyncMixin)
AsyncSelfT = TypeVar('AsyncSelfT', bound=AsyncMixin)


class BoundZyncMethod(Generic[SelfT, P, ReturnT]):
    """A bound `zync.zmethod`."""

    def __init__(self, func: ZyncableMethod[SelfT, P, ReturnT], instance: SelfT) -> None:
        """..

        :param func: The method to wrap.
        :param instance: The instance to bind the method to.
        """
        self.func: Final[ZyncableMethod[SelfT, P, ReturnT]] = func
        self.instance: Final[SelfT] = instance

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.func.__qualname__} of {self.instance!r}>'

    def run_zync(self, mode: Mode, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT]:
        """Run the method in the given mode."""
        return self.func(self.instance, mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the method in sync mode."""
        return _run_sync_coroutine(self.func(self.instance, SYNC, *args, **kwargs))

    async def run_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the method in async mode."""
        return await self.func(self.instance, ASYNC, *args, **kwargs)

    @overload
    def __call__(self: 'BoundZyncMethod[SyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs) -> ReturnT: ...
    @overload
    def __call__(self: 'BoundZyncMethod[AsyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT | Coroutine[Any, Any, ReturnT]:  # noqa: D102
        if isinstance(self.instance, SyncMixin):
            return self.run_sync(*args, **kwargs)
        elif isinstance(self.instance, AsyncMixin):
            return self.run_async(*args, **kwargs)
        else:
            raise TypeError(f'{type(self).__name__} is only callable when bound to instances of SyncMixin or AsyncMixin')


class BoundZyncClassMethod(Generic[SelfT, P, ReturnT]):
    """A bound `zync.zclassmethod`."""

    def __init__(self, func: ZyncableMethod[type[SelfT], P, ReturnT], cls: type[SelfT]) -> None:
        """..

        :param func: The method to wrap.
        :param cls: The class to bind the method to.
        """
        self.func: Final[ZyncableMethod[type[SelfT], P, ReturnT]] = func
        self.cls: Final[type[SelfT]] = cls

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.func.__qualname__} of {self.cls!r}>'

    def run_zync(self, mode: Mode, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT]:
        """Run the method in the given mode."""
        return self.func(self.cls, mode, *args, **kwargs)

    def run_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the method in sync mode."""
        return _run_sync_coroutine(self.func(self.cls, SYNC, *args, **kwargs))

    async def run_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT:
        """Run the method in async mode."""
        return await self.func(self.cls, ASYNC, *args, **kwargs)

    @overload
    def __call__(self: 'BoundZyncClassMethod[SyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs) -> ReturnT: ...
    @overload
    def __call__(self: 'BoundZyncClassMethod[AsyncSelfT, P, ReturnT]', *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, ReturnT]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT | Coroutine[Any, Any, ReturnT]:  # noqa: D102
        if issubclass(self.cls, SyncMixin):
            return self.run_sync(*args, **kwargs)
        elif issubclass(self.cls, AsyncMixin):
            return self.run_async(*args, **kwargs)
        else:
            raise TypeError(f'{type(self).__name__} is only callable when bound to subclasses of SyncMixin or AsyncMixin')


class zproperty(Generic[SelfT, ReturnT]):
    """Wrap a method to act as a property in sync mode, and as a coroutine in async mode."""

    def __init__(self, func: ZyncableMethod[SelfT, [], ReturnT]) -> None:
        """..

        :param func: The method to wrap.
        """
        self.func: Final[ZyncableMethod[SelfT, [], ReturnT]] = func
        self.__name__: str = func.__name__
        self.__qualname__: str = getattr(func, '__qualname__', func.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.__qualname__}>'

    @overload
    def __get__(self, instance: None, owner: type[SelfT]) -> Self: ...
    @overload
    def __get__(self: 'zproperty[SyncSelfT, ReturnT]', instance: SelfT, owner: type[SelfT] | None) -> ReturnT: ...
    @overload
    def __get__(self: 'zproperty[AsyncSelfT, ReturnT]', instance: SelfT, owner: type[SelfT] | None) -> 'BoundZyncMethod[SelfT, [], ReturnT]': ...
    def __get__(self, instance: SelfT | None, owner: type[SelfT] | None) -> 'Self | ReturnT | BoundZyncMethod[SelfT, [], ReturnT]':
        if instance is None:
            return self
        elif isinstance(instance, SyncMixin):
            return BoundZyncMethod(self.func, instance).run_sync()
        elif isinstance(instance, AsyncMixin):
            return BoundZyncMethod(self.func, instance)
        raise TypeError(f'{type(self).__name__} can only be accessed on instances of SyncMixin or AsyncMixin')
