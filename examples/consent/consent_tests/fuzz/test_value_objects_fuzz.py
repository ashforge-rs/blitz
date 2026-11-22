"""Properties of the value objects and the profile rules."""

from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st

from consent_app.entities import ConsentMethod, NoticeVersion, Purpose, PurposeSlug, SubjectId
from consent_app.profiles import GDPR
from consent_tests.fakes import EPOCH


@given(st.text(max_size=200))
def test_a_subject_id_never_holds_an_email_or_whitespace(raw: str) -> None:
    try:
        subject = SubjectId(raw)
    except ValueError:
        return
    assert "@" not in subject.value
    assert not any(c.isspace() for c in subject.value)


@given(st.from_regex(r"[a-z][a-z0-9_]{1,63}", fullmatch=True))
def test_every_snake_case_slug_is_accepted(raw: str) -> None:
    assert PurposeSlug(raw).value == raw


@given(st.sampled_from(ConsentMethod), st.integers(min_value=0, max_value=36_500))
def test_under_gdpr_a_never_given_consent_never_allows_processing(
    method: ConsentMethod, days: int
) -> None:
    purpose = Purpose(PurposeSlug("ads"), "Ads", NoticeVersion("v1"), EPOCH, EPOCH)

    assert GDPR.status(purpose, None, EPOCH + timedelta(days=days)).may_process is False
    assert GDPR.accepts(method) == (
        method
        not in {ConsentMethod.PRE_TICKED_BOX, ConsentMethod.IMPLIED, ConsentMethod.INACTIVITY}
    )
