from apps.backend.models import ChapterDraft, OutlineOption
from apps.backend.services import (
    DomainError,
    ensure_chapter_limit,
    is_passing_score,
    select_highest_scored_draft,
    select_highest_scored_option,
)


def test_ensure_chapter_limit_accepts_ten() -> None:
    assert ensure_chapter_limit(10) == 10


def test_ensure_chapter_limit_rejects_eleven() -> None:
    try:
        ensure_chapter_limit(11)
    except DomainError as error:
        assert error.code == "INVALID_ARGUMENT"
    else:
        raise AssertionError("Expected DomainError")


def test_select_highest_scored_option() -> None:
    options = [
        OutlineOption(
            id="1",
            option_no=1,
            content="A",
            core_conflict="A",
            key_event="A",
            ending_hook="A",
            score_plot=7.0,
            score_consistency=7.0,
            score_hook=7.0,
            final_score=7.0,
            editor_comment="A",
        ),
        OutlineOption(
            id="2",
            option_no=2,
            content="B",
            core_conflict="B",
            key_event="B",
            ending_hook="B",
            score_plot=8.2,
            score_consistency=8.2,
            score_hook=8.2,
            final_score=8.2,
            editor_comment="B",
        ),
    ]
    assert select_highest_scored_option(options).id == "2"


def test_score_boundary_is_passing() -> None:
    assert is_passing_score(8.0) is True


def test_select_highest_scored_draft() -> None:
    drafts = [
        ChapterDraft(
            id="d1",
            revision_no=1,
            content="v1",
            score_readability=7.0,
            score_tension=7.0,
            score_consistency=7.0,
            final_score=7.0,
            issue_summary="low",
        ),
        ChapterDraft(
            id="d2",
            revision_no=2,
            content="v2",
            score_readability=8.4,
            score_tension=8.4,
            score_consistency=8.4,
            final_score=8.4,
            issue_summary="good",
        ),
    ]
    assert select_highest_scored_draft(drafts).id == "d2"
