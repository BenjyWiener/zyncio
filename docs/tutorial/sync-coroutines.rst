===============
Sync Coroutines
===============


Definition
==========

ZyncIO is built on the concept of "sync coroutines" -- coroutine functions that don't actually do any
asynchronous work, and can therefore be executed without an event loop.

Specifically, if an ``async def`` function exclusively ``await``\ s other coroutines, and those
coroutines also exclusively ``await`` other coroutines, and so on, we call it a "sync coroutine":

.. testcode::

    # This is a sync coroutine function...
    async def sync_coroutine() -> str:
        return "world"

    # ... and so is this
    async def another_sync_coroutine() -> str:
        return f"Hello, {await sync_coroutine()}!"

..

    The behavior of `await coroutine` is effectively the same as invoking a regular,
    synchronous Python function.

    -- `A Conceptual Overview of asyncio`_

.. _A Conceptual Overview of asyncio: https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html#await


Executing a Sync Coroutine
==========================

Sync coroutine functions still return a coroutine object, so how do we actually execute them without
something like `asyncio.run`?

Python's coroutines are very similar to generators. Like generators, they have a `~coroutine.send` method that can be
used to advance their execution. This will cause the coroutine to execute until it ``await``\ s a `~asyncio.Future`. If
the coroutine is a sync coroutine, it never ``await``\ s a ``Future``, so it will run to completion, raising
`StopIteration` with the return value.

Using our example from above, we can execute the sync coroutine like this:

.. doctest::

    >>> coro = another_sync_coroutine()
    >>> try:
    ...     coro.send(None)
    ... except StopIteration as e:
    ...     result = e.value
    >>> result
    'Hello, world!'

Using ``try``/``except`` is clunky, so ZyncIO provides a utility function, `zyncio.run_sync`.


How is this useful?
===================

The sync coroutines we've seen so far are basically just regular sync functions with extra steps. To make them useful,
we need :doc:`conditionally-sync-coroutines`.
