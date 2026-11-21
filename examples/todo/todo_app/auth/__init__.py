"""Bearer API-token authentication, independent of how tokens are stored.

``BearerTokenAuthProvider`` plugs into ``create_app(auth_provider=...)``.  It
depends only on the :class:`TokenVerifier` port; the composition root
(``factory.py``) hands it the users context's implementation.  No context is
imported here, so todos routes get a :class:`Principal` without knowing that
users exist.
"""

from .bearer_token_provider import BearerTokenAuthProvider
from .dependencies import CurrentPrincipalDep
from .principal import Principal
from .token_verifier import TokenVerifier

__all__ = ["BearerTokenAuthProvider", "CurrentPrincipalDep", "Principal", "TokenVerifier"]
