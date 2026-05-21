"""Catalogue clients.

Public exports:

- :class:`SaleSourceClient` — runtime-checkable protocol; the contract the
  matcher and stock services depend on.
- :class:`UniqloClient` — the concrete implementation talking to Uniqlo's
  Commerce API.
"""

from uniqlo_sales_alerter.clients.protocol import SaleSourceClient
from uniqlo_sales_alerter.clients.uniqlo import UniqloClient

__all__ = ["SaleSourceClient", "UniqloClient"]
