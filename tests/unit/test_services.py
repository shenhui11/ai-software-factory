from apps.backend.models import ProjectCreate, RewriteRequest, TaskCreateRequest, TaskMode
from apps.backend.services import NovelService
from apps.backend.store import InMemoryStore


def make_service() -> NovelService:
    return NovelService(InMemoryStore())


def make_project(service: NovelService, genre: str = "fantasy") -> str:
    project = service.create_project(
        ProjectCreate(
            title="Test Novel",
            genre=genre,
            length_type="long",
            template_id="tpl-system-romance",
            summary="A summary",
            character_cards=["Hero"],
            world_rules=["Rule"],
            event_summary=["Event"],
            mode_default=TaskMode.manual,
        )
    )
    return project.id


def test_horror_project_hits_max_rewrites_and_manual_review() -> None:
    service = make_service()
    project_id = make_project(service, genre="horror")
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    result = service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]
    assert result.status.value == "completed"
    assert len(chapter.drafts) == 6
    assert chapter.rewrite_count == 5
    assert chapter.needs_manual_review is True


def test_final_draft_keeps_highest_score() -> None:
    service = make_service()
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]
    final_draft = next(draft for draft in chapter.drafts if draft.selected)
    assert final_draft.final_score == max(draft.final_score for draft in chapter.drafts)


def test_rewrite_returns_diff_and_consistency_note() -> None:
    service = make_service()
    project_id = make_project(service)
    result = service.rewrite_paragraph(
        project_id,
        "chapter_x",
        RewriteRequest(paragraph="Old text", instruction="Sharper conflict"),
    )
    assert result.updated != result.original
    assert result.diff
    assert "continuity" in result.consistency_note.lower()
