==============
Typing Support
==============

ZyncIO is designed around Python's typing system; ensuring LSPs can correctly infer the types of ZyncIO constructs is a
first-class priority.

With that said, some type checkers don't support the full range of types used in the library. Currently, `Pyright`_ is
the primary supported type checker. In addition, best-effort support is provided for `Mypy`_, `Pyrefly`_, `ty`_, and
`Zuban`_.

.. _Pyright: https://github.com/microsoft/pyright
.. _Mypy: https://github.com/python/mypy
.. _Pyrefly: https://github.com/facebook/pyrefly
.. _ty: https://github.com/astral-sh/ty
.. _Zuban: https://github.com/zubanls/zuban


Known Issues
============

Mypy
    `~typing.Self` annotations solve to `~typing.Never`.

ty
    `~typing.Self` annotations are not solved properly
    (`astral-sh/ty#2520 <https://github.com/astral-sh/ty/issues/2520>`__).

Zuban
    `~zyncio.zclassmethod` produces type checking errors due an issue with Zuban's handling of `@classmethod`-decorated
    methods (`zubanls/zuban#446 <https://github.com/zubanls/zuban/issues/446>`__).
