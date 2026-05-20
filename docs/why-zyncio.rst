=================
Why (not) ZyncIO?
=================

ZyncIO is not the first attempt to tackle the sync/async code-duplication problem. This page lists some alternative
approaches and compares them to ZyncIO.


Why *not* ZyncIO?
=================

The main disadvantage of ZyncIO is the increased function call overhead. Calling (and running) a coroutine is quite a
bit slower than a regular function call. The overhead is generally negligible for functions that perform I/O, but for
performance-critical applications ZyncIO may have a noticeable impact on sync, single-threaded code.


Other Approaches
================


Code Generation
---------------

This is the approach taken by the `psycopg`_ project (`blog post`_). Essentially, you write one (typically async)
version of your library and then use some form of preprossor to generate the other version, often via an AST
transformation.

This approach has the advantage of no runtime overhead, but adds a build step to what would otherwise be a pure-Python
library. Additionally, AST transformations like this are very tricky to get right, and often require tuning to work for
a particular project (see, for example |RenameAsyncToSync.names_map|_ in psycopg's ``async_to_sync.py``).

.. _psycopg: https://www.psycopg.org/
.. _blog post: https://www.psycopg.org/articles/2024/09/23/async-to-sync/
.. |RenameAsyncToSync.names_map| replace:: ``RenameAsyncToSync.names_map``
.. _RenameAsyncToSync.names_map:
    https://github.com/psycopg/psycopg/blob/896eee2363d0bc25cc31ccf4189b295bb61deb40/tools/async_to_sync.py#L269


Run-time AST Transformations
----------------------------

This is similar to the code generation approach described above, except that the transformations are performed at run
time, such as via a decorator. The `transfunctions`_ library implements this approach.

Aside from the pitfalls of AST transformations described above, this approach has the added issues that come with
dynamically generated code, namely lack of bytecode caching and difficulties debugging.

.. _transfunctions: https://github.com/mutating/transfunctions


Background Event Loop
---------------------

Instead of writing separate sync and async code, you can send `await`\ ables to an event loop running in a background
thread, allowing you to run async from sync code. This approach avoids duplicating implementations, but doesn't solve
the problem of API duplication -- users either need to wrap every call in a `run_async` helper function, or you need to
write a wrapper for every user-facing function in your library.


Sans-I/O
--------

`Sans-I/O`_ is an approach to writing network protocol implementations that are agnostic to the underlying I/O framework.
Similar to the background event loop approach, sans-I/O only solves the implementation duplication issue, not the API
duplication issue. To make use of a sans-I/O library, it needs to be paired with an I/O layer -- and that layer must
provide either a sync or async API.

You *can*, however, use ZyncIO to write a single wrapper around a sans-I/O library that provides both sync and async
APIs.

.. _Sans-I/O: https://sans-io.readthedocs.io/
