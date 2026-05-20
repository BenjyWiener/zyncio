=====================================
Using ZyncIO -- Class-Based Interface
=====================================

In the previous chapter we learned about `zyncio.zfunc` and its siblings in the standalone API.
Where ZyncIO really shines, however, is its class-based interface.

Let's build a client for fetching repository information from the GitHub API. We'll use `niquests`_ for making the
HTTP requests.

.. _niquests: https://github.com/jawah/niquests


.. testsetup:: *

    # Mock requests to avoid rate-limiting issues in doctests.

    import niquests


    class MockJsonResponse:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            return self

        def json(self):
            return self.data


    requests = {
        'https://api.github.com/repos/BenjyWiener/zyncio': {
            'full_name': 'BenjyWiener/zyncio',
            'description': 'Write dual sync/async Python interfaces with minimal duplication.',
            'stargazers_count': 100,
        },
        'https://api.github.com/repos/BenjyWiener/zyncio/languages': {
            'Python': 57333,
        }
    }


    def get(url):
        return MockJsonResponse(requests[url])


    async def aget(url):
        return get(url)


    niquests.get = get
    niquests.aget = aget


Base Class
==========

We start by defining ``BaseGitHubClient``, which will serve as the basis for our sync and async clients. We'll implement
the ``get_repo`` method. Notice that we use `zyncio.zmethod` instead of `zyncio.zfunc`, and we don't have a
``zync_mode`` parameter. Instead, we use `zyncio.is_sync` to determine if we're in sync or async mode.


.. testcode:: simple-client

    from dataclasses import dataclass

    import niquests
    import zyncio


    @dataclass
    class Repo:
        full_name: str
        description: str
        stars: int


    class BaseGitHubClient:
        @zyncio.zmethod
        async def get_repo(self, owner: str, repo: str) -> Repo:
            url = f'https://api.github.com/repos/{owner}/{repo}'
            if zyncio.is_sync(self):
                data = niquests.get(url).raise_for_status().json()
            else:
                data = (await niquests.aget(url)).raise_for_status().json()

            return Repo(
                full_name=data['full_name'],
                description=data['description'],
                stars=data['stargazers_count'],
            )

If we try using ``BaseGitHubClient``, we get an exception:

.. doctest:: simple-client

    >>> client = BaseGitHubClient()
    >>> client.get_repo('BenjyWiener', 'zyncio')
    Traceback (most recent call last):
      ...
    TypeError: BoundZyncMethod is only callable on instances of classes that subclass zyncio.SyncMixin or zyncio.AsyncMixin, or that implement the zyncio.ZyncDelegator protocol


The Mixins
==========

To actually use our client, we need to specialize it, using the special mixins `zyncio.SyncMixin` and
`zyncio.AsyncMixin`:

.. testcode:: simple-client

    class GitHubClient(BaseGitHubClient, zyncio.SyncMixin):
        pass


    class AsyncGitHubClient(BaseGitHubClient, zyncio.AsyncMixin):
        pass

.. doctest:: simple-client

    >>> client = GitHubClient()
    >>> client.get_repo('BenjyWiener', 'zyncio')
    Repo(full_name='BenjyWiener/zyncio', description='...', stars=...)

    >>> import asyncio
    >>> async_client = AsyncGitHubClient()
    >>> asyncio.run(async_client.get_repo('BenjyWiener', 'zyncio'))
    Repo(full_name='BenjyWiener/zyncio', description='...', stars=...)


Composing ``zyncio.zmethod``\ s
===============================

Let's add another method to get the language breakdown of a repository:

.. testsetup:: get-languages, get-languages-dry-naive, get-languages-dry

    from dataclasses import dataclass
    from typing import Any

    import niquests
    import zyncio


    @dataclass
    class Repo:
        full_name: str
        description: str
        stars: int

.. testcode:: get-languages

    class BaseGitHubClient:
        @zyncio.zmethod
        async def get_repo(self, owner: str, repo: str) -> Repo:
            url = f'https://api.github.com/repos/{owner}/{repo}'
            if zyncio.is_sync(self):
                data = niquests.get(url).raise_for_status().json()
            else:
                data = (await niquests.aget(url)).raise_for_status().json()

            return Repo(
                full_name=data['full_name'],
                description=data['description'],
                stars=data['stargazers_count'],
            )

        @zyncio.zmethod
        async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
            url = f'https://api.github.com/repos/{owner}/{repo}/languages'
            if zyncio.is_sync(self):
                return niquests.get(url).raise_for_status().json()
            else:
                return (await niquests.aget(url)).raise_for_status().json()

.. testcode:: get-languages
    :hide:

    class GitHubClient(BaseGitHubClient, zyncio.SyncMixin):
        pass


    class AsyncGitHubClient(BaseGitHubClient, zyncio.AsyncMixin):
        pass

.. doctest:: get-languages

    >>> client = GitHubClient()
    >>> client.get_languages('BenjyWiener', 'zyncio')
    {'Python': ...}

This works, but it's not very DRY. Let's extract our request logic into a new method, ``get_url``:

.. testcode:: get-languages-dry-naive

    class BaseGitHubClient:
        @zyncio.zmethod
        async def get_url(self, path: str, base_url: str = 'https://api.github.com') -> Any:
            url = f'{base_url}/{path}'
            if zyncio.is_sync(self):
                return niquests.get(url).raise_for_status().json()
            else:
                return (await niquests.aget(url)).raise_for_status().json()

        @zyncio.zmethod
        async def get_repo(self, owner: str, repo: str) -> Repo:
            data = await self.get_url(f'repos/{owner}/{repo}')

            return Repo(
                full_name=data['full_name'],
                description=data['description'],
                stars=data['stargazers_count'],
            )

        @zyncio.zmethod
        async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
            return await self.get_url(f'repos/{owner}/{repo}/languages')

.. testcode:: get-languages-dry-naive
    :hide:

    class GitHubClient(BaseGitHubClient, zyncio.SyncMixin):
        pass


    class AsyncGitHubClient(BaseGitHubClient, zyncio.AsyncMixin):
        pass

.. doctest:: get-languages-dry-naive

    >>> client = GitHubClient()
    >>> client.get_languages('BenjyWiener', 'zyncio')
    Traceback (most recent call last):
        ...
    TypeError: 'dict' object can't be awaited

What happened?

The problem is that ``get_url`` is a `zyncio.zmethod`, so when we call ``self.get_url(...)`` in ``get_languages``,
it acts like a synchronous method and returns a ``dict`` instead of a coroutine. If we remove the ``await`` our code
will work when we use ``GitHubClient``, but then it will break when we use ``AsyncGitHubClient``.

We can use `zyncio.is_sync` to determine if we need to ``await`` or not -- but then we're back to our original problem!
That's where `~zyncio.BoundZyncMethod.call_zync` comes in. ``call_zync`` always returns a coroutine, so we can safely
``await`` it regardless of ``self``'s mode.

Let's fix our code:

.. testcode:: get-languages-dry

    class BaseGitHubClient:
        @zyncio.zmethod
        async def get_url(self, path: str, base_url: str = 'https://api.github.com') -> Any:
            url = f'{base_url}/{path}'
            if zyncio.is_sync(self):
                return niquests.get(url).raise_for_status().json()
            else:
                return (await niquests.aget(url)).raise_for_status().json()

        @zyncio.zmethod
        async def get_repo(self, owner: str, repo: str) -> Repo:
            data = await self.get_url.call_zync(f'repos/{owner}/{repo}')

            return Repo(
                full_name=data['full_name'],
                description=data['description'],
                stars=data['stargazers_count'],
            )

        @zyncio.zmethod
        async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
            return await self.get_url.call_zync(f'repos/{owner}/{repo}/languages')

.. testcode:: get-languages-dry
    :hide:

    class GitHubClient(BaseGitHubClient, zyncio.SyncMixin):
        pass


    class AsyncGitHubClient(BaseGitHubClient, zyncio.AsyncMixin):
        pass

.. doctest:: get-languages-dry

    >>> client = GitHubClient()
    >>> client.get_repo('BenjyWiener', 'zyncio')
    Repo(full_name='BenjyWiener/zyncio', description='...', stars=...)

    >>> import asyncio
    >>> async_client = AsyncGitHubClient()
    >>> asyncio.run(async_client.get_repo('BenjyWiener', 'zyncio'))
    Repo(full_name='BenjyWiener/zyncio', description='...', stars=...)

.. tip::
    You can use ``.z(...)`` as an alias of ``.call_zync(...)``.

.. tip::
    If your method is private and only ever called from other ZyncIO code, don't decorate it with
    ``@zyncio.zmethod``. That way you can call it normally, without ``call_zync``.


The ``ZyncDelegator`` Protocol
==============================

Let's make our library a bit more object-oriented, by adding a ``languages`` property to ``Repo``.

Instead of splitting ``Repo`` into two classes (sync and async), we can make it delegate its mode to its client, using
the `zyncio.ZyncDelegator` protocol:

.. testcode:: delegator
    :pyversion: >= 3.14

    from dataclasses import dataclass
    from typing import Any, Self

    import niquests
    import zyncio


    @dataclass
    class Repo[ClientT: BaseGitHubClient]:
        full_name: str
        description: str
        stars: int
        client: ClientT

        # Using a `TypeVar` for the return type of `__zync_delegate__` lets
        # type checkers and IDEs infer the correct types ZyncIO descriptors
        # like `zyncio.zmethod` and `zyncio.zproperty`.
        def __zync_delegate__(self) -> ClientT:
            return self.client

        @zyncio.zproperty
        async def languages(self) -> dict[str, int]:
            owner, repo = self.full_name.split('/', 1)
            return await self.client.get_languages.call_zync(owner, repo)


    class BaseGitHubClient:
        @zyncio.zmethod
        async def get_url(self, path: str, base_url: str = 'https://api.github.com') -> Any:
            url = f'{base_url}/{path}'
            if zyncio.is_sync(self):
                return niquests.get(url).raise_for_status().json()
            else:
                return (await niquests.aget(url)).raise_for_status().json()

        @zyncio.zmethod
        async def get_repo(self, owner: str, repo: str) -> Repo[Self]:
            data = await self.get_url.call_zync(f'repos/{owner}/{repo}')

            return Repo(
                full_name=data['full_name'],
                description=data['description'],
                stars=data['stargazers_count'],
                client=self,
            )

        @zyncio.zmethod
        async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
            return await self.get_url.call_zync(f'repos/{owner}/{repo}/languages')


    class GitHubClient(BaseGitHubClient, zyncio.SyncMixin):
        pass


    class AsyncGitHubClient(BaseGitHubClient, zyncio.AsyncMixin):
        pass

.. doctest:: delegator
    :pyversion: >= 3.14

    >>> client = GitHubClient()
    >>> repo = client.get_repo('BenjyWiener', 'zyncio')
    >>> repo.languages
    {'Python': ...}

    >>> import asyncio
    >>> async_client = AsyncGitHubClient()
    >>> async_repo = asyncio.run(async_client.get_repo('BenjyWiener', 'zyncio'))
    >>> asyncio.run(async_repo.languages())
    {'Python': ...}

.. note::
    Unlike `zyncio.zmethod`, `zyncio.zproperty` doesn't have an equivalent of `~zyncio.BoundZyncMethod.call_zync`.
    Instead, you can access and call the `zyncio.zproperty` object directly via the class::

        await type(self).languages(self)

    However, if you find yourself using this pattern a lot, you should probably consider using a regular method instead
    of (or alongside) your property.


Other Decorators
================

In addition to `zyncio.zmethod` and `zyncio.zproperty` there's `zyncio.zclassmethod`, as well method-versions of
`zyncio.zgenerator` and `zyncio.zcontextmanager`, `zyncio.zgeneratormethod` and `zyncio.zcontextmanagermethod`. You can
read more about all of these in the :doc:`/api/index`.
