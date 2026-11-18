"""Shared pytest configuration for the backend."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
