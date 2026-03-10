"""Test utils."""

import asyncio


def assert_running_loop() -> None:
    """Assert that there is a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover
        raise AssertionError('Expected a running event loop')


def assert_no_running_loop() -> None:
    """Assert that there is no running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError('Expected no running event loop')
