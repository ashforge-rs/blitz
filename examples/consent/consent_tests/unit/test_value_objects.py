import pytest

from consent_app.entities import (
    ConsentDecision,
    ConsentEvent,
    NoticeVersion,
    Purpose,
    PurposeSlug,
    SubjectId,
)
from consent_tests.fakes import EPOCH


@pytest.mark.parametrize("raw", ["ada@example.com", "a@b"])
def test_subject_ids_must_not_be_email_addresses(raw: str) -> None:
    with pytest.raises(ValueError, match="pseudonymous"):
        SubjectId(raw)


@pytest.mark.parametrize("raw", ["", "has space", "x" * 129, "tab\tbed"])
def test_subject_ids_are_compact_printable_tokens(raw: str) -> None:
    with pytest.raises(ValueError, match="subject id"):
        SubjectId(raw)


@pytest.mark.parametrize("raw", ["Newsletter", "1st", "a", "with-dash", "x" * 65])
def test_purpose_slugs_are_snake_case_identifiers(raw: str) -> None:
    with pytest.raises(ValueError, match="purpose"):
        PurposeSlug(raw)


def test_notice_versions_are_printable_tokens() -> None:
    assert NoticeVersion("2026-06.1").value == "2026-06.1"
    with pytest.raises(ValueError, match="notice version"):
        NoticeVersion("june 2026")


def test_purpose_descriptions_are_trimmed_and_bounded() -> None:
    purpose = Purpose(PurposeSlug("ads"), "  Ads  ", NoticeVersion("v1"), EPOCH, EPOCH)
    assert purpose.description == "Ads"
    with pytest.raises(ValueError, match="description"):
        Purpose(PurposeSlug("ads"), "   ", NoticeVersion("v1"), EPOCH, EPOCH)


@pytest.mark.parametrize("field", ["source", "recorded_by"])
@pytest.mark.parametrize("bad", ["", " padded ", "x" * 65, "line\nbreak"])
def test_events_require_a_clean_source_and_recorder(field: str, bad: str) -> None:
    values = {"source": "web", "recorded_by": "crm", field: bad}
    with pytest.raises(ValueError, match=field):
        ConsentEvent(
            id="e1",
            subject=SubjectId("s1"),
            purpose=PurposeSlug("ads"),
            decision=ConsentDecision.WITHDRAWN,
            notice_version=None,
            method=None,
            profile="gdpr",
            recorded_at=EPOCH,
            **values,
        )
