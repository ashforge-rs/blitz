from typing import Annotated

from fastapi import Depends, Request

from state import get_domain

from .service import ItemService


def _get_item_service(request: Request) -> ItemService:
    # Imported lazily: domain.py imports this module, so a top-level import
    # would be circular.
    from .domain import ItemsDomain

    return get_domain(request, ItemsDomain).service


ItemServiceDep = Annotated[ItemService, Depends(_get_item_service)]
