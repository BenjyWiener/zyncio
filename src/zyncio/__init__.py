"""Write dual sync/async interfaces with minimal duplication."""

import abc
from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, closing, contextmanager
from enum import Enum
from functools import cached_property, wraps
import sys
from types import MethodType
from typing import (
    TYPE_CHECKING,
    Any,
    Concatenate,
    Final,
    Generic,
    ParamSpec,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)


if sys.version_info < (3, 13):  # pragma: no cover
    from typing_extensions import Self, TypeIs
else:
    from typing import Self, TypeIs


__all__ = [
    # Modes
    'Mode',
    'SYNC',
    'ASYNC',
    # Mixins and protocols
    'SyncMixin',
    'AsyncMixin',
    'ZyncDelegator',
    # Utilities
    'ZYNC_MODE_CACHE_ATTR',
    'get_mode',
    'is_sync',
    'is_async',
    'run_sync',
    'make_sync',
    # Function Decorators
    'zfunc',
    'zgenerator',
    'zcontextmanager',
    # Method Decorators
    'zmethod',
    'zclassmethod',
    'zproperty',
    'ZyncSettableProperty',
    'zgeneratormethod',
    'zcontextmanagermethod',
]


_UNKNOWN_FUNC_NAME: Final = '<unknown>'


class Mode(Enum):
    """ZyncIO execution mode."""

    SYNC = 'sync'
    ASYNC = 'async'


SYNC: Final = Mode.SYNC
"""Module-level alias."""

ASYNC: Final = Mode.ASYNC
"""Module-level alias."""


_REQUIRED_INTERFACE_MESSAGE = (
    'instances of classes that subclass zyncio.SyncMixin or zyncio.AsyncMixin, '
    'or that implement the zyncio.ZyncDelegator protocol'
)


# NOTE: We use covariant `TypeVar`s in some places where we should technically use
# invariant ones (such as `zclassmethod`, which should use `T`, not `T_co`).
# Without this, some common accepted (although theoretically unsafe) patterns, such as
# overriding `classmethod`s and `property`s would be flagged by type checkers.
# In this case we've chosen convenience over correctness.
T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)
ReturnT = TypeVar('ReturnT')
ReturnT_co = TypeVar('ReturnT_co', covariant=True)
YieldT = TypeVar('YieldT')
YieldT_co = TypeVar('YieldT_co', covariant=True)
SendT_contra = TypeVar('SendT_contra', contravariant=True)
CallableT = TypeVar('CallableT', bound=Callable[..., Any])
P = ParamSpec('P')


class SyncMixin:
    """Mixin that makes bindable ZyncIO constructs use `SYNC` mode.

    See the documentation for each construct for details on how they interact
    with this mixin.
    """


class AsyncMixin:
    """Mixin that makes bindable ZyncIO constructs use `ASYNC` mode.

    See the documentation for each construct for details on how they interact
    with this mixin.
    """


@runtime_checkable
class ZyncDelegator(Protocol[T_co]):
    """Protocol for delegating ZyncIO `Mode` to another object.

    This protocol should be used for objects that wrap another ZyncIO-compatible object,
    and perform all operations via that "delegate" object.
    """

    @abc.abstractmethod
    def __zync_delegate__(self) -> 'T_co | ZyncDelegator[T_co]':
        """Return an object to which calls to `zyncio.get_mode` should be delegated.

        The returned object must either be an instance of `zyncio.SyncMixin` or `zyncio.AsyncMixin`, or implement this
        protocol itself.
        """


SyncObject: TypeAlias = SyncMixin | ZyncDelegator[SyncMixin]
r"""An instance of `zyncio.SyncMixin` or `zyncio.ZyncDelegator`\ [`zyncio.SyncMixin`]"""


AsyncObject: TypeAlias = AsyncMixin | ZyncDelegator[AsyncMixin]
r"""An instance of `zyncio.AsyncMixin` or `zyncio.ZyncDelegator`\ [`zyncio.AsyncMixin`]"""


SyncT = TypeVar('SyncT', bound=SyncObject)
AsyncT = TypeVar('AsyncT', bound=AsyncObject)
SyncClassT = TypeVar('SyncClassT', bound=SyncMixin)
AsyncClassT = TypeVar('AsyncClassT', bound=AsyncMixin)


ZYNC_MODE_CACHE_ATTR: Final = '__zync_cached_mode__'
"""Name of the attribute used by `zyncio.get_mode` to cache the mode of a `ZyncDelegator` object.

You can use this constant to allow caching when defining ``__slots__``.
"""


def get_mode(obj: object) -> Mode | None:
    """Get the `Mode` of `obj`, if it can be determined.

    If `obj` is an instance of `zyncio.SyncMixin` or `zyncio.AsyncMixin`, returns the corresponding mode.

    If `obj` implements the `zyncio.ZyncDelegator` protocol, this function will be called recursively with the
    object returned by the method. The result will be cached on `obj`, and any intermediate objects, if possible.

    :param obj: The object to inspect.
    :return: The `Mode` of `obj` if it has one, otherwise `None`.
    """
    if isinstance(obj, SyncMixin):
        return SYNC

    if isinstance(obj, AsyncMixin):
        return ASYNC

    if isinstance(obj, ZyncDelegator):
        if mode := getattr(obj, ZYNC_MODE_CACHE_ATTR, None):
            return mode

        mode = get_mode(obj.__zync_delegate__())
        try:
            object.__setattr__(obj, ZYNC_MODE_CACHE_ATTR, mode)
        except AttributeError:
            pass  # pragma: no cover
        return mode

    return None


def get_class_mode(cls: type) -> Mode | None:
    """Get the `zyncio.Mode` of `cls`, if it can be determined.

    This function behaves the same as `zyncio.get_mode`, but for classes instead of instances.

    :param cls: The class to inspect.
    :return: The `Mode` of `cls` if it has one, otherwise `None`.
    """
    if issubclass(cls, SyncMixin):
        return SYNC

    if issubclass(cls, AsyncMixin):
        return ASYNC

    return None  # pragma: no cover


def is_sync(obj: object) -> TypeIs[SyncObject]:
    r"""Check if `obj` is a subclass of `zyncio.SyncMixin` or implements `zyncio.ZyncDelegator`\ [`zyncio.SyncMixin`]`.

    :param obj: The object to inspect.
    """
    return get_mode(obj) is SYNC


def is_async(obj: object) -> TypeIs[AsyncObject]:
    r"""Check if `obj` is a subclass of `zyncio.AsyncMixin` or implements `zyncio.ZyncDelegator`\ [`zyncio.SyncMixin`].

    :param obj: The object to inspect.
    """
    return get_mode(obj) is ASYNC


def is_sync_class(cls: type) -> TypeIs[type[SyncMixin]]:
    """Check if `cls` is a subclass of `zyncio.SyncMixin`.

    :param cls: The class to inspect.
    """
    return issubclass(cls, SyncMixin)


def is_async_class(cls: type) -> TypeIs[type[AsyncMixin]]:
    """Check if `cls` is a subclass of `zyncio.AsyncMixin`.

    :param cls: The class to inspect.
    """
    return issubclass(cls, AsyncMixin)


Zyncable = Callable[Concatenate[Mode, P], Coroutine[Any, Any, ReturnT_co]]
ZyncableMethod = Callable[Concatenate[T_co, P], Coroutine[Any, Any, ReturnT_co]]


def run_sync(coro: Coroutine[Any, Any, ReturnT_co]) -> ReturnT_co:
    """Run a coroutine synchronously.

    The coroutine must only ``await`` other coroutines, recursively.
    Awaiting any non-coroutine (such as an `asyncio.Future`), at any point in the call chain,
    will cause the function to fail.

    :param coro: The sync coroutine to run.
    :return: The return value of the coroutine.
    """
    with closing(coro):
        try:
            coro.send(None)
        except StopIteration as e:
            return e.value
        else:
            raise RuntimeError('ZyncIO functions must only await pure coroutines in sync mode')


def make_sync(func: Callable[P, Coroutine[Any, Any, ReturnT_co]]) -> Callable[P, ReturnT_co]:
    """Wrap an async function make it run synchronously using `zyncio.run_sync`.

    This function is useful for overloaded functions and methods, whose signatures can't
    be captured properly by `zyncio.zmethod` etc.

    Example::

        class BaseClient(zyncio.ZyncBase):
            @overload
            async def _overloaded_method(self, x: str) -> bytes: ...
            @overload
            async def _overloaded_method(self, x: int) -> bool: ...
            async def _overloaded_method(self, x: str | int) -> bytes | bool:
                ...

        class SyncClient(zyncio.SyncMixin, BaseClient):
            overloaded_method = zyncio.make_sync(BaseClient._overloaded_method)

        class AsyncClient(zyncio.AsyncMixin, BaseClient):
            overloaded_method = BaseClient._overloaded_method

    If any of your overload signatures use `Self`, you may need to define your
    method outside of the class for type checkers to infer the correct type for `Self`
    in subclasses::

        class BaseClient(zyncio.ZyncBase):
            ...

        ClientT = TypeVar('ClientT', bound=BaseClient)

        @overload
        async def overloaded_method(self: ClientT, x: str) -> ClientT: ...
        @overload
        async def overloaded_method(self, x: int) -> bool: ...
        async def overloaded_method(self: ClientT, x: str | int) -> ClientT | bool:
            ...

        class SyncClient(zyncio.SyncMixin, BaseClient):
            overloaded_method = zyncio.make_sync(overloaded_method)

        class AsyncClient(zyncio.AsyncMixin, BaseClient):
            overloaded_method = overloaded_method

    :param func: The function to wrap.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        return run_sync(func(*args, **kwargs))

    return wrapper


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


class _BoundZyncFunctionWrapper(Generic[T_co, CallableT]):
    def __init__(self, func: CallableT, instance: T_co) -> None:
        """..

        :param func: The method to wrap.
        :param instance: The instance to bind the method to.
        """
        self.func: Final[CallableT] = func
        self.__self__: T_co = instance
        self.__name__: str = getattr(func, '__name__', _UNKNOWN_FUNC_NAME)
        self.__qualname__: str = getattr(func, '__qualname__', self.__name__)
        self.__doc__: str | None = getattr(func, '__doc__', None)

    if not TYPE_CHECKING:
        # Masquerade as `MethodType` to improve `help(...)` and IPython `?` output.
        __class__ = MethodType

        def __getattr__(self, name: str) -> object:  # pragma: no cover
            try:
                return getattr(MethodType(self.func, self.__self__), name)
            except AttributeError:
                pass
            # Raise an `AttributeError` for `self` instead of `self.func`.
            return super().__getattribute__(name)

    def __repr__(self) -> str:
        return f'<{self.__module__}.{type(self).__name__} {self.func.__qualname__} of {self.__self__!r}>'


class zfunc(_ZyncFunctionWrapper[Zyncable[P, ReturnT_co]]):
    """Wrap a function to be callable in both sync and async mode.

    The function must take a `zyncio.Mode` as its first parameter.

    Example::

        @zyncio.zfunc
        async def zync_sleep(zync_mode: zyncio.Mode, duration: float) -> None:
            if zync_mode is zyncio.SYNC:
                time.sleep(duration)
            else:
                await asyncio.sleep(duration)

        zync_sleep.call_sync(1.0)

        await zync_sleep.call_async(1.0)
    """

    async def call_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Call the function in the given `Mode`.

        :param zync_mode: The `Mode` to use.
        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        return await self.func(zync_mode, *args, **kwargs)

    def call_sync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Call the function in `SYNC` mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        return run_sync(self.func(SYNC, *args, **kwargs))

    async def call_async(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Call the function in `ASYNC` mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        return await self.func(ASYNC, *args, **kwargs)


class zmethod(_ZyncFunctionWrapper[ZyncableMethod[T_co, P, ReturnT_co]]):
    r"""Wrap a method to be callable in both sync and async mode.

    Decorated methods act like sync methods on `SyncObject`\ s and like async methods on `AsyncObject`\ s.

    Accessing on an instance returns a `BoundZyncMethod`.

    Example::

        class BaseClient:
            @zyncio.zmethod
            async def sleep(self, duration: float) -> None:
                if zyncio.is_sync(self):
                    time.sleep(duration)
                else:
                    await asyncio.sleep(duration)

        class SyncClient(BaseClient, zyncio.SyncMixin): pass
        class AsyncClient(BaseClient, zyncio.AsyncMixin): pass

        SyncClient().sleep(1.0)

        await AsyncClient().sleep(1.0)
    """

    @overload
    def __get__(self, instance: None, owner: type[T]) -> Self: ...
    @overload
    def __get__(
        self: 'zmethod[T, P, ReturnT_co]', instance: T, owner: type[T] | None
    ) -> 'BoundZyncMethod[T, P, ReturnT_co]': ...
    def __get__(
        self: 'zmethod[T, P, ReturnT_co]', instance: T | None, owner: type[T] | None
    ) -> 'zmethod[T, P, ReturnT_co] | BoundZyncMethod[T, P, ReturnT_co]':
        if instance is None:
            return self
        return BoundZyncMethod(self.func, instance)


class BoundZyncMethod(_BoundZyncFunctionWrapper[T_co, ZyncableMethod[T_co, P, ReturnT_co]]):
    """A bound `zyncio.zmethod`.

    Acts like a sync method when bound to a `SyncObject` and like an async method when bound to an `AsyncObject`.
    """

    async def call_zync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the method as a coroutine regardless of mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        return await self.func(self.__self__, *args, **kwargs)

    z = call_zync
    """Alias for `call_zync`."""

    @overload
    def __call__(self: 'BoundZyncMethod[SyncT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs) -> ReturnT_co: ...
    @overload
    def __call__(
        self: 'BoundZyncMethod[AsyncT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs
    ) -> Coroutine[Any, Any, ReturnT_co]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co | Coroutine[Any, Any, ReturnT_co]:
        match get_mode(self.__self__):
            case Mode.SYNC:
                return run_sync(self.func(self.__self__, *args, **kwargs))
            case Mode.ASYNC:
                return self.func(self.__self__, *args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable on {_REQUIRED_INTERFACE_MESSAGE}')


class zclassmethod(_ZyncFunctionWrapper[ZyncableMethod[type[T_co], P, ReturnT_co]]):
    r"""Wrap a class method to be callable in both sync and async mode.

    Decorated methods act like sync `classmethod`\ s on subclasses of `SyncMixin` and like async `classmethod`\ s on
    subclasses of `AsyncMixin`.

    Accessing returns a `BoundZyncClassMethod`.

    Example::

        class BaseClient:
            @zyncio.zclassmethod
            @classmethod
            async def sleep(cls, duration: float) -> None:
                if zyncio.is_sync_class(self):
                    time.sleep(duration)
                else:
                    await asyncio.sleep(duration)

        class SyncClient(BaseClient, zyncio.SyncMixin): pass
        class AsyncClient(BaseClient, zyncio.AsyncMixin): pass

        SyncClient.sleep(1.0)

        await AsyncClient.sleep(1.0)

    .. note:: This decorator does not work with `ZyncDelegator`.
    """

    def __get__(
        self: 'zclassmethod[T, P, ReturnT_co]', instance: T | None, owner: type[T]
    ) -> 'BoundZyncClassMethod[T, P, ReturnT_co]':
        return BoundZyncClassMethod(self.func, owner)


class BoundZyncClassMethod(_BoundZyncFunctionWrapper[type[T], ZyncableMethod[type[T], P, ReturnT_co]]):
    """A bound `zyncio.zclassmethod`.

    Acts like a sync `classmethod` when bound to a subclass of `SyncMixin` and like an async `classmethod` when bound to
    a subclass of `AsyncMixin`.
    """

    def __init__(self, func: ZyncableMethod[type[T], P, ReturnT_co], cls: type[T]) -> None:
        """..

        :param func: The method to wrap.
        :param cls: The class to bind the method to.
        """
        super().__init__(func, cls)

    async def call_zync(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co:
        """Run the method as a coroutine regardless of mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        return await self.func(self.__self__, *args, **kwargs)

    z = call_zync
    """Alias for `call_zync`."""

    @overload
    def __call__(
        self: 'BoundZyncClassMethod[SyncClassT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs
    ) -> ReturnT_co: ...
    @overload
    def __call__(
        self: 'BoundZyncClassMethod[AsyncClassT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs
    ) -> Coroutine[Any, Any, ReturnT_co]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> ReturnT_co | Coroutine[Any, Any, ReturnT_co]:
        match get_class_mode(self.__self__):
            case Mode.SYNC:
                return run_sync(self.func(self.__self__, *args, **kwargs))
            case Mode.ASYNC:
                return self.func(self.__self__, *args, **kwargs)
            case _:
                raise TypeError(
                    f'{type(self).__name__} is only callable on classes that subclass zyncio.SyncMixin or zyncio.AsyncMixin'
                )


class zproperty(_ZyncFunctionWrapper[ZyncableMethod[T_co, [], ReturnT_co]]):
    r"""Wrap a method to act as a property in sync mode, and as a coroutine in async mode.

    Decorated methods act like sync `property`\ s on `SyncObject`\ s and like async methods on `AsyncObject`\ s.

    Accessing on an instance of `AsyncObject` returns a `BoundZyncMethod`.

    When accessed via the owning class, instances of `zproperty` are callable, calling through to the wrapped (unbound)
    getter.

    Example::

        class BaseClient:
            ...

            @zyncio.zproperty
            async def status(self) -> str:
                return await self.get_status.z()

        class SyncClient(BaseClient, zyncio.SyncMixin): pass
        class AsyncClient(BaseClient, zyncio.AsyncMixin): pass

        print(SyncClient().status)

        print(await AsyncClient().status())
    """

    def __init__(self, getter: ZyncableMethod[T_co, [], ReturnT_co]) -> None:
        """..

        :param getter: The getter for this property.
        """
        super().__init__(getter)
        self.fget: Final[ZyncableMethod[T_co, [], ReturnT_co]] = getter

    @overload
    def __get__(self: 'zproperty[T, ReturnT_co]', instance: None, owner: type[T]) -> 'zproperty[T, ReturnT_co]': ...
    @overload
    def __get__(self: 'zproperty[SyncT, ReturnT_co]', instance: SyncT, owner: type[SyncT] | None) -> ReturnT_co: ...
    @overload
    def __get__(
        self: 'zproperty[AsyncT, ReturnT_co]', instance: AsyncT, owner: type[AsyncT] | None
    ) -> 'BoundZyncMethod[AsyncT, [], ReturnT_co]': ...
    def __get__(
        self: 'zproperty[T, ReturnT_co]', instance: T | None, owner: type[T] | None
    ) -> 'zproperty[T, ReturnT_co] | ReturnT_co | BoundZyncMethod[T, [], ReturnT_co]':
        if instance is None:
            return self

        match get_mode(instance):
            case Mode.SYNC:
                return run_sync(self.fget(instance))
            case Mode.ASYNC:
                return BoundZyncMethod(self.fget, instance)
            case _:
                raise TypeError(f'{type(self).__name__} is only accessible on {_REQUIRED_INTERFACE_MESSAGE}')

    async def __call__(self: 'zproperty[T, ReturnT_co]', instance: T) -> ReturnT_co:
        """Call this `zproperty`'s getter with the given instance."""
        return await self.fget(instance)

    def setter(self, setter: ZyncableMethod[T_co, [ReturnT_co], None]) -> 'ZyncSettableProperty[T_co, ReturnT_co]':
        """Return a new `ZyncSettableProperty` with the given setter.

        Example::

            class BaseClient:
                ...

                @zyncio.zproperty
                async def status(self) -> str:
                    return await self.get_status.z()

                @status.setter
                async def status(self, value: str) -> None:
                    await self.set_status.z(value)

            class SyncClient(BaseClient, zyncio.SyncMixin): pass
            class AsyncClient(BaseClient, zyncio.AsyncMixin): pass

            SyncClient().status = 'RUNNING'

            await AsyncClient().status.set('RUNNING')

        .. warning::
            Some type checkers may complain if you use the same name for the getter and setter.
        """
        return ZyncSettableProperty(self.fget, setter)


class ZyncSettableProperty(zproperty[T, ReturnT]):
    """A `zyncio.zproperty` with a setter.

    See `zyncio.zproperty.setter`.

    Accessing on an instance of `AsyncObject` returns a `BoundZyncSettableProperty`.
    """

    def __init__(self, getter: ZyncableMethod[T, [], ReturnT], setter: ZyncableMethod[T, [ReturnT], None]) -> None:
        """..

        :param getter: The getter for this property.
        :param setter: The setter for this property.
        """
        super().__init__(getter)
        self.fset: Final[ZyncableMethod[T, [ReturnT], None]] = setter

    @overload
    def __get__(self, instance: None, owner: type[T]) -> Self: ...
    @overload
    def __get__(
        self: 'ZyncSettableProperty[SyncT, ReturnT]', instance: SyncT, owner: type[SyncT] | None
    ) -> ReturnT: ...
    @overload
    def __get__(
        self: 'ZyncSettableProperty[AsyncT, ReturnT]', instance: AsyncT, owner: type[AsyncT] | None
    ) -> 'BoundZyncSettableProperty[AsyncT, ReturnT]': ...
    def __get__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, instance: T | None, owner: type[T] | None
    ) -> 'ZyncSettableProperty[T, ReturnT] | ReturnT | BoundZyncSettableProperty[Any, ReturnT]':
        if instance is None:
            return self

        match get_mode(instance):
            case Mode.SYNC:
                return run_sync(self.fget(instance))
            case Mode.ASYNC:
                return BoundZyncSettableProperty(self.fget, self.fset, instance)
            case _:
                raise TypeError(f'{type(self).__name__} is only accessible on {_REQUIRED_INTERFACE_MESSAGE}')

    def __set__(self: 'ZyncSettableProperty[SyncT, ReturnT]', instance: SyncT, value: ReturnT) -> None:
        match get_mode(instance):
            case Mode.SYNC:
                return run_sync(self.fset(instance, value))
            case Mode.ASYNC:
                raise TypeError(f'{type(self).__name__}.__set__ does not support async mode')
            case _:  # pragma: no cover
                raise TypeError(f'{type(self).__name__} is only settable on {_REQUIRED_INTERFACE_MESSAGE}')


class BoundZyncSettableProperty(BoundZyncMethod[T, [], ReturnT]):
    """A bound `zyncio.ZyncSettableProperty`.

    This class provides the ``set`` functionality for `ZyncSettableProperty` when accessed on an instance of
    `AsyncObject`.
    """

    def __init__(
        self,
        getter: ZyncableMethod[T, P, ReturnT],
        setter: ZyncableMethod[T, [ReturnT], None],
        instance: T,
    ) -> None:
        """..

        :param func: The method to wrap.
        :param instance: The instance to bind the method to.
        """
        super().__init__(getter, instance)
        self.fset: Final[ZyncableMethod[T, [ReturnT], None]] = setter

    async def set(self, value: ReturnT) -> None:
        """Set the value of the property."""
        match get_mode(self.__self__):
            case Mode.SYNC:  # pragma: no cover
                raise TypeError(f'{type(self).__name__}.set does not support sync mode')
            case Mode.ASYNC:
                return await self.fset(self.__self__, value)
            case _:  # pragma: no cover
                raise TypeError(f'{type(self).__name__} is only settable on {_REQUIRED_INTERFACE_MESSAGE}')


ZyncableGeneratorFunc: TypeAlias = Callable[Concatenate[Mode, P], AsyncGenerator[ReturnT_co, SendT_contra]]
ZyncableGeneratorMethod: TypeAlias = Callable[Concatenate[T, P], AsyncGenerator[ReturnT_co, SendT_contra]]


@contextmanager
def _async_context_manager_to_sync(cm: AbstractAsyncContextManager[ReturnT_co]) -> Generator[ReturnT_co]:
    val = run_sync(cm.__aenter__())
    try:
        yield val
    except BaseException:
        if not run_sync(cm.__aexit__(*sys.exc_info())):
            raise
    else:
        run_sync(cm.__aexit__(None, None, None))


class zcontextmanager(_ZyncFunctionWrapper[ZyncableGeneratorFunc[P, ReturnT_co, None]]):
    """Similar to :deco:`contextlib.contextmanager`, but callable in both sync and async modes.

    The function must take a `zyncio.Mode` as its first parameter.

    Example::

        @zyncio.zcontextmanager
        async def run_process(zync_mode: zyncio.Mode, command: str) -> AsyncGenerator[int]:
            if zync_mode is zyncio.SYNC:
                process = subprocess.Popen(command, shell=True)
            else:
                process = await asyncio.create_subprocess_shell(command)

            try:
                yield process.pid
            finally:
                process.terminate()

        with run_process.call_sync('some command') as pid:
            print(pid)

        async def main() -> None:
            async with run_process.call_async('some command') as pid:
                print(pid)
    """

    def __init__(self, func: ZyncableGeneratorFunc[P, ReturnT_co, None]) -> None:
        """..

        :param func: The generator function to wrap.
        """
        super().__init__(func)
        self.cm_func: Callable[Concatenate[Mode, P], AbstractAsyncContextManager[ReturnT_co]] = asynccontextmanager(
            func
        )

    @asynccontextmanager
    async def call_zync(self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co]:
        """Enter the context manager in the given mode.

        :param zync_mode: The `Mode` to use.
        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        async with self.cm_func(zync_mode, *args, **kwargs) as val:
            yield val

    def call_sync(self, *args: P.args, **kwargs: P.kwargs) -> AbstractContextManager[ReturnT_co]:
        """Enter the context manager in sync mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        return _async_context_manager_to_sync(self.cm_func(SYNC, *args, **kwargs))

    @asynccontextmanager
    async def call_async(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co]:
        """Enter the context manager in async mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        async with self.cm_func(ASYNC, *args, **kwargs) as val:
            yield val


class zcontextmanagermethod(_ZyncFunctionWrapper[ZyncableGeneratorMethod[T_co, P, ReturnT_co, None]]):
    r"""Similar to :deco:`contextlib.contextmanager`, but callable in both sync and async modes.

    Decorated methods return sync context managers when called on `SyncObject`\ s and async context managers when called
    on `AsyncObject`\ s.

    Accessing on an instance returns a `BoundZyncContextManagerMethod`.

    Example::

        class BaseClient:
            @zyncio.zcontextmanagermethod
            async def run_process(command: str) -> AsyncGenerator[int]:
                if zync_mode is zyncio.SYNC:
                    process = subprocess.Popen(command, shell=True)
                else:
                    process = await asyncio.create_subprocess_shell(command)

                try:
                    yield process.pid
                finally:
                    process.terminate()

        class SyncClient(BaseClient, zyncio.SyncMixin): pass
        class AsyncClient(BaseClient, zyncio.AsyncMixin): pass

        with SyncClient().run_process('some command') as pid:
            print(pid)

        async with AsyncClient().run_process('some command') as pid:
            print(pid)
    """

    def __init__(self, func: ZyncableGeneratorMethod[T_co, P, ReturnT_co, None]) -> None:
        """..

        :param func: The generator method to wrap.
        """
        super().__init__(func)

    @overload
    def __get__(self, instance: None, owner: type[T]) -> Self: ...
    @overload
    def __get__(
        self: 'zcontextmanagermethod[T, P, ReturnT_co]', instance: T, owner: type[T] | None
    ) -> 'BoundZyncContextManagerMethod[T, P, ReturnT_co]': ...
    def __get__(
        self: 'zcontextmanagermethod[T, P, ReturnT_co]', instance: T | None, owner: type[T] | None
    ) -> 'zcontextmanagermethod[T, P, ReturnT_co] | BoundZyncContextManagerMethod[T, P, ReturnT_co]':
        if instance is None:
            return self
        return BoundZyncContextManagerMethod(self.func, instance)


class BoundZyncContextManagerMethod(_BoundZyncFunctionWrapper[T, ZyncableGeneratorMethod[T, P, ReturnT_co, None]]):
    """A bound `zyncio.zcontextmanagermethod`.

    Returns a sync context manager when bound to a `SyncObject` and an async context manager when bound to an
    `AsyncObject`.
    """

    @cached_property
    def _cm(self) -> Callable[Concatenate[T, P], AbstractAsyncContextManager[ReturnT_co]]:
        return asynccontextmanager(self.func)

    def call_zync(self, *args: P.args, **kwargs: P.kwargs) -> AbstractAsyncContextManager[ReturnT_co]:
        """Enter the context manager as an async context manager regardless of mode."""
        return self._cm(self.__self__, *args, **kwargs)

    z = call_zync
    """Alias for `call_zync`."""

    @overload
    def __call__(
        self: 'BoundZyncContextManagerMethod[SyncT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs
    ) -> AbstractContextManager[ReturnT_co]: ...
    @overload
    def __call__(
        self: 'BoundZyncContextManagerMethod[AsyncT, P, ReturnT_co]', *args: P.args, **kwargs: P.kwargs
    ) -> AbstractAsyncContextManager[ReturnT_co]: ...
    def __call__(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> AbstractContextManager[ReturnT_co] | AbstractAsyncContextManager[ReturnT_co]:
        match get_mode(self.__self__):
            case Mode.SYNC:
                return _async_context_manager_to_sync(self._cm(self.__self__, *args, **kwargs))
            case Mode.ASYNC:
                return self._cm(self.__self__, *args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable on {_REQUIRED_INTERFACE_MESSAGE}')


class zgenerator(_ZyncFunctionWrapper[ZyncableGeneratorFunc[P, ReturnT_co, SendT_contra]]):
    """Wrap a generator function to be callable in both sync and async mode.

    The function must take a `zyncio.Mode` as its first parameter.

    Example::

        @zyncio.zgenerator
        async def countdown(zync_mode: zyncio.Mode, start: int) -> AsyncGenerator[int]:
            for i in range(start, 0, -1):
                await zync_sleep.call_zync(zync_mode, 1.0)
                yield i

        for n in countdown.call_sync(5):
            print(n)

        async for n in countdown.call_async(5):
            print(n)
    """

    def __init__(self, func: ZyncableGeneratorFunc[P, ReturnT_co, SendT_contra]) -> None:
        """..

        :param func: The generator function to wrap.
        """
        super().__init__(func)

    def call_zync(
        self, zync_mode: Mode, /, *args: P.args, **kwargs: P.kwargs
    ) -> AsyncGenerator[ReturnT_co, SendT_contra]:
        """Call the generator function in the given mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        return self.func(zync_mode, *args, **kwargs)

    def call_sync(self, *args: P.args, **kwargs: P.kwargs) -> Generator[ReturnT_co, SendT_contra]:
        """Call the generator function in sync mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        async_gen = self.func(SYNC, *args, **kwargs)
        try:
            send_val = yield run_sync(anext(async_gen))
            while True:
                send_val = yield run_sync(async_gen.asend(send_val))
        except StopAsyncIteration:
            pass
        finally:
            run_sync(async_gen.aclose())

    def call_async(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co, SendT_contra]:
        """Call the generator function in async mode.

        :param args: Positional arguments to forward to the wrapped function.
        :param kwargs: Keyword arguments to forward to the wrapped function.
        """
        return self.func(ASYNC, *args, **kwargs)


class zgeneratormethod(_ZyncFunctionWrapper[ZyncableGeneratorMethod[T_co, P, ReturnT_co, SendT_contra]]):
    r"""Wrap a generator method to be callable in both sync and async mode.

    Decorated methods return sync generators when called on `SyncObject`\ s and async generators when called on
    `AsyncObject`\ s.

    Accessing on an instance returns a `BoundZyncGeneratorMethod`.

    Example::

        class BaseClient:
            @zyncio.zgeneratormethod
            async def countdown(start: int) -> AsyncGenerator[int]:
                for i in range(start, 0, -1):
                    if zyncio.is_sync(self):
                        time.sleep(1.0)
                    else:
                        await asyncio.sleep(1.0)
                    yield i


        class SyncClient(BaseClient, zyncio.SyncMixin): pass
        class AsyncClient(BaseClient, zyncio.AsyncMixin): pass

        for n in SyncClient().countdown(5):
            print(n)

        async for n in AsyncClient().countdown(5):
            print(n)
    """

    def __init__(self, func: ZyncableGeneratorMethod[T_co, P, ReturnT_co, SendT_contra]) -> None:
        """..

        :param func: The generator method to wrap.
        """
        super().__init__(func)

    @overload
    def __get__(self, instance: None, owner: type[T]) -> Self: ...
    @overload
    def __get__(
        self: 'zgeneratormethod[T, P, ReturnT_co, SendT_contra]', instance: T, owner: type[T] | None
    ) -> 'BoundZyncGeneratorMethod[T, P, ReturnT_co, SendT_contra]': ...
    def __get__(
        self: 'zgeneratormethod[T, P, ReturnT_co, SendT_contra]', instance: T | None, owner: type[T] | None
    ) -> 'zgeneratormethod[T, P, ReturnT_co, SendT_contra] | BoundZyncGeneratorMethod[T, P, ReturnT_co, SendT_contra]':
        if instance is None:
            return self
        return BoundZyncGeneratorMethod(self.func, instance)


class BoundZyncGeneratorMethod(_BoundZyncFunctionWrapper[T, ZyncableGeneratorMethod[T, P, ReturnT_co, SendT_contra]]):
    """A bound `zyncio.zgeneratormethod`.

    Returns a sync generator when bound to a `SyncObject` and an async generator when bound to an `AsyncObject`.
    """

    def call_zync(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ReturnT_co, SendT_contra]:
        """Run the generator function in the given mode."""
        return self.func(self.__self__, *args, **kwargs)

    z = call_zync
    """Alias for `call_zync`."""

    def _run_sync(self, *args: P.args, **kwargs: P.kwargs) -> Generator[ReturnT_co, SendT_contra]:
        async_gen = self.func(self.__self__, *args, **kwargs)
        try:
            send_val = yield run_sync(anext(async_gen))
            while True:
                send_val = yield run_sync(async_gen.asend(send_val))
        except StopAsyncIteration:
            pass
        finally:
            run_sync(async_gen.aclose())

    @overload
    def __call__(
        self: 'BoundZyncGeneratorMethod[SyncT, P, ReturnT_co, SendT_contra]', *args: P.args, **kwargs: P.kwargs
    ) -> Generator[ReturnT_co, SendT_contra]: ...
    @overload
    def __call__(
        self: 'BoundZyncGeneratorMethod[AsyncT, P, ReturnT_co, SendT_contra]', *args: P.args, **kwargs: P.kwargs
    ) -> AsyncGenerator[ReturnT_co, SendT_contra]: ...
    def __call__(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> Generator[ReturnT_co, SendT_contra] | AsyncGenerator[ReturnT_co, SendT_contra]:
        match get_mode(self.__self__):
            case Mode.SYNC:
                return self._run_sync(*args, **kwargs)
            case Mode.ASYNC:
                return self.func(self.__self__, *args, **kwargs)
            case _:
                raise TypeError(f'{type(self).__name__} is only callable on {_REQUIRED_INTERFACE_MESSAGE}')
