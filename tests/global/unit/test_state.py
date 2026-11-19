from types import SimpleNamespace

import pytest

from state import get_domain


class _Orders:
    pass


class _Users:
    pass


def _request(registry):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(domains_by_type=registry)))


def test_get_domain_returns_instance_by_type():
    orders = _Orders()
    assert get_domain(_request({_Orders: orders, _Users: _Users()}), _Orders) is orders


def test_get_domain_missing_raises_lookup_error():
    with pytest.raises(LookupError, match="_Orders"):
        get_domain(_request({}), _Orders)


def test_get_domain_wrong_type_raises_type_error():
    with pytest.raises(TypeError):
        get_domain(_request({_Orders: _Users()}), _Orders)


async def test_example_domain_indexed_by_type(client, app):
    from domains.example.domain import ItemsDomain

    r = await client.get("/v1/example/")
    assert r.status_code == 200
    assert isinstance(app.state.domains_by_type[ItemsDomain], ItemsDomain)
