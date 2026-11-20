"""
Domain modules served by the ``api`` service.

``make domain DOMAIN=<name>`` appends new domains here.  The test suite's ``app``
fixture uses the same list, so a registered domain is testable immediately.
"""

from typing import TYPE_CHECKING

from domains.example import domain as example_domain

if TYPE_CHECKING:
    import types

DOMAINS: list[types.ModuleType] = [
    example_domain,
]
