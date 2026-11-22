"""Consent app: an example service on blitz.  Records and answers consent decisions.

Layout::

    entities/    value objects, the consent event, the consent status (stdlib only)
    profiles/    RegulationProfile (the rules as data) and GDPR, its first instance
    ports/       abstract base classes: unit of work, purposes, ledger, clock, ids
    use_cases/   one module per use case, + their errors
    adapters/    sql/ (SQLAlchemy, Alembic), http/ (FastAPI), auth, api_keys, system
    container.py composition root; domain.py the blitz hooks; factory.py the app
"""
