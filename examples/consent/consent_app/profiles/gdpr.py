"""The GDPR consent rules, as a :class:`RegulationProfile`.

Illustrative, not legal advice: it encodes the general GDPR consent conditions,
not member-state rules (such as the age of digital consent, Art. 8) or sector law.
"""

from consent_app.entities import ConsentMethod

from .regulation_profile import ConsentModel, RegulationProfile

GDPR = RegulationProfile(
    name="gdpr",
    # Consent is "a clear affirmative act" (Art. 4(11)); without it there is no lawful
    # basis of consent (Art. 6(1)(a)).
    model=ConsentModel.OPT_IN,
    # Silence, pre-ticked boxes or inactivity do not constitute consent (Recital 32).
    accepted_methods=frozenset(
        {
            ConsentMethod.CHECKBOX,
            ConsentMethod.TOGGLE,
            ConsentMethod.SIGNED_FORM,
            ConsentMethod.RECORDED_VERBAL,
            ConsentMethod.DOUBLE_OPT_IN,
        }
    ),
    # The GDPR sets no fixed expiry; consent lasts until withdrawn (Art. 7(3)) ...
    max_validity=None,
    # ... but it must be informed (Art. 4(11), 7(2)): a material change to the
    # information given means asking again.
    renew_on_notice_change=True,
)
