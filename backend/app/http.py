"""Shared HTTP client factory.

Building a TLS context costs about 0.7 s on Windows (CA bundle loading): it is
built once and shared by every client.
"""

from functools import lru_cache
from ssl import SSLContext

import httpx


@lru_cache
def _ssl_context() -> SSLContext:
    return httpx.create_ssl_context()


def new_http_client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(verify=_ssl_context(), **kwargs)
