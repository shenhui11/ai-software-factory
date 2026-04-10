from __future__ import annotations


def create_seeded_chapter(client) -> str:
    project = client.post(
        "/api/v1/projects",
        json={
            "title": "Seed",
            "genre": "Fantasy",
            "style": "Lyrical",
            "target_audience": "Adult",
            "length_target": "Short story",
            "tone": "Melancholic",
            "premise": "A courier carries a memory across a broken kingdom.",
        },
    ).json()
    client.put(
        f"/api/v1/projects/{project['id']}/canon",
        json={
            "world_summary": "Ruined roads divide the kingdom.",
            "style_constraints": ["Use close POV"],
            "narrative_rules": ["No omniscient narrator"],
            "characters": [
                {
                    "name": "Eda",
                    "role": "Courier",
                    "personality_traits": ["wary"],
                    "speech_style": "quiet",
                    "motivation": "Deliver the memory intact",
                    "key_relationships": ["Prince Rowan"],
                    "notes": "Keeps promises",
                }
            ],
        },
    )
    outline = client.post(f"/api/v1/projects/{project['id']}/outline:generate").json()
    chapter = client.post(
        f"/api/v1/projects/{project['id']}/chapters",
        json={
            "outline_item_id": outline["chapters"][0]["id"],
            "title": "Chapter 1",
            "summary": "Eda enters the capital.",
        },
    ).json()
    client.post(
        f"/api/v1/chapters/{chapter['id']}/draft:generate",
        json={
            "chapter_goal": "Open the journey",
            "context_window_strategy": "outline only",
        },
    )
    return chapter["id"]

def test_create_project_missing_required_field_returns_uniform_error(client):
    response = client.post(
        "/api/v1/projects",
        json={
            "genre": "Fantasy",
            "style": "Lyrical",
            "target_audience": "Adult",
            "length_target": "Short story",
            "tone": "Calm",
            "premise": "Missing title",
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed."


def test_invalid_selection_is_rejected(client):
    chapter_id = create_seeded_chapter(client)
    response = client.post(
        f"/api/v1/chapters/{chapter_id}/edits",
        json={
            "selection_start": 50,
            "selection_end": 10,
            "operation": "rewrite",
            "instruction": "invalid range",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_selection"


def test_invalid_export_format_is_rejected(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "title": "Export Target",
            "genre": "Drama",
            "style": "Lean",
            "target_audience": "Adult",
            "length_target": "Novel",
            "tone": "Reflective",
            "premise": "A retired actor returns home.",
        },
    ).json()
    response = client.get(f"/api/v1/projects/{project['id']}/export", params={"format": "pdf"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_export_format"


def test_fix_range_must_cover_issue_excerpt(client):
    chapter_id = create_seeded_chapter(client)
    scan = client.post(f"/api/v1/chapters/{chapter_id}/qa-scans").json()
    issue = scan["issues"][0]
    response = client.post(
        f"/api/v1/qa-issues/{issue['id']}/fix",
        json={
            "strategy": "tighten",
            "allowed_range": {
                "start": issue["start_offset"] + 1,
                "end": issue["end_offset"] - 1,
            },
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "range_too_narrow"
