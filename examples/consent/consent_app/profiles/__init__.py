"""Regulation profiles: each regulation's consent rules as data over a neutral core."""

from .gdpr import GDPR
from .regulation_profile import ConsentModel, RegulationProfile

#: Profiles a deployment can choose with CONSENT_PROFILE.  Add a regulation here.
PROFILES: dict[str, RegulationProfile] = {GDPR.name: GDPR}

__all__ = ["GDPR", "PROFILES", "ConsentModel", "RegulationProfile"]
