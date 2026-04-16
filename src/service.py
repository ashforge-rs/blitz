from __future__ import annotations


class Service:
    """
    Base class for domain services.

    A service encapsulates business logic and external I/O for a bounded context.
    Declare dependencies (database clients, config, other services, etc.) in
    ``__init__`` and implement domain-specific methods in the subclass.

    Example::

        class OrderService(Service):
            def __init__(self, db: AsyncSession, config: Settings) -> None:
                self.db = db
                self.config = config

            async def find_by_id(self, order_id: str) -> dict | None:
                raise NotImplementedError

            async def create(self, payload: dict) -> dict:
                raise NotImplementedError
    """
