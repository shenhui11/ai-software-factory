from __future__ import annotations


def create_project(client):
    response = client.post(
        "/api/v1/projects",
        json={
            "title": "Clockwork Harbor",
            "genre": "Steampunk Mystery",
            "style": "Cinematic",
            "target_audience": "Young Adult",
            "length_target": "Novella",
            "tone": "Tense but hopeful",
            "premise": "An apprentice cartographer uncovers a conspiracy in a floating city.",
        },
    )
    assert response.status_code == 200
    return response.json()


def update_canon(client, project_id: str):
    response = client.put(
        f"/api/v1/projects/{project_id}/canon",
        json={
            "world_summary": "A floating trade city powered by unstable tide engines.",
            "style_constraints": ["Keep imagery tactile", "Avoid omniscient exposition"],
            "narrative_rules": ["Stay close to protagonist POV"],
            "characters": [
                {
                    "name": "Liora",
                    "role": "Apprentice cartographer",
                    "personality_traits": ["curious", "guarded"],
                    "speech_style": "precise and dry",
                    "motivation": "Protect her missing mentor's map archive",
                    "key_relationships": ["Mentor Iven", "Rival pilot Sera"],
                    "notes": "Distrusts officials",
                }
            ],
        },
    )
    assert response.status_code == 200
    return response.json()


def create_chapter_flow(client):
    project = create_project(client)
    project_id = project["id"]
    canon = update_canon(client, project_id)
    outline_response = client.post(f"/api/v1/projects/{project_id}/outline:generate")
    assert outline_response.status_code == 200
    outline = outline_response.json()
    chapter_response = client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={
            "outline_item_id": outline["chapters"][0]["id"],
            "title": "Chapter 1: Setup",
            "summary": "Liora finds a damaged chart that points to the tide engines.",
        },
    )
    assert chapter_response.status_code == 200
    chapter = chapter_response.json()
    draft_response = client.post(
        f"/api/v1/chapters/{chapter['id']}/draft:generate",
        json={
            "chapter_goal": "Introduce the engine sabotage mystery.",
            "context_window_strategy": "Use outline and canon context",
        },
    )
    assert draft_response.status_code == 200
    return {
        "project": project,
        "canon": canon,
        "outline": outline,
        "chapter": chapter,
        "draft": draft_response.json(),
    }


def test_full_story_workbench_flow(client):
    flow = create_chapter_flow(client)
    project_id = flow["project"]["id"]
    chapter_id = flow["chapter"]["id"]

    chapter_details = client.get(f"/api/v1/chapters/{chapter_id}")
    assert chapter_details.status_code == 200
    original_content = chapter_details.json()["content"]
    assert "World context" in original_content

    save_response = client.patch(
        f"/api/v1/chapters/{chapter_id}",
        json={"content": original_content + "\n\nLiora hides the chart before dawn."},
    )
    assert save_response.status_code == 200

    edit_response = client.post(
        f"/api/v1/chapters/{chapter_id}/edits",
        json={
            "selection_start": 0,
            "selection_end": 20,
            "operation": "rewrite",
            "instruction": "make the opening sharper",
        },
    )
    assert edit_response.status_code == 200
    candidates = edit_response.json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["selection_start"] == 0
    chapter_after_edit = client.get(f"/api/v1/chapters/{chapter_id}").json()
    assert chapter_after_edit["content"].endswith("Liora hides the chart before dawn.")

    scan_response = client.post(f"/api/v1/chapters/{chapter_id}/qa-scans")
    assert scan_response.status_code == 200
    scan = scan_response.json()
    issue_types = {issue["issue_type"] for issue in scan["issues"]}
    assert issue_types == {
        "logic_gap",
        "canon_conflict",
        "plot_discontinuity",
        "redundancy",
        "foreshadowing_miss",
        "voice_drift",
    }

    scan_read = client.get(f"/api/v1/chapters/{chapter_id}/qa-scans/{scan['id']}")
    assert scan_read.status_code == 200
    issue = scan_read.json()["issues"][0]
    fix_response = client.post(
        f"/api/v1/qa-issues/{issue['id']}/fix",
        json={
            "strategy": "clarify causality",
            "allowed_range": {
                "start": issue["start_offset"],
                "end": issue["end_offset"],
            },
        },
    )
    assert fix_response.status_code == 200
    affected_range = fix_response.json()["affected_range"]
    assert affected_range["start"] == issue["start_offset"]
    assert affected_range["end"] == issue["end_offset"]

    snapshot_response = client.post(
        f"/api/v1/chapters/{chapter_id}/versions",
        json={"version_note": "Checkpoint before restore"},
    )
    assert snapshot_response.status_code == 200
    snapshot_version = snapshot_response.json()
    versions_response = client.get(f"/api/v1/chapters/{chapter_id}/versions")
    assert versions_response.status_code == 200
    versions = versions_response.json()["items"]
    assert len(versions) >= 4

    current_version_id = client.get(f"/api/v1/chapters/{chapter_id}").json()["current_version"]["id"]
    diff_response = client.get(
        f"/api/v1/versions/{snapshot_version['id']}/diff",
        params={"base_version_id": current_version_id},
    )
    assert diff_response.status_code == 200
    assert isinstance(diff_response.json()["diff"], list)

    first_version_id = versions[0]["id"]
    restore_response = client.post(f"/api/v1/versions/{first_version_id}:restore")
    assert restore_response.status_code == 200
    restored_chapter = client.get(f"/api/v1/chapters/{chapter_id}").json()
    assert restored_chapter["current_version"]["source_type"] == "restore"

    export_md = client.get(f"/api/v1/projects/{project_id}/export", params={"format": "md"})
    export_txt = client.get(f"/api/v1/projects/{project_id}/export", params={"format": "txt"})
    assert export_md.status_code == 200
    assert export_txt.status_code == 200
    assert "# Clockwork Harbor" in export_md.json()["content"]
    assert "Clockwork Harbor" in export_txt.json()["content"]


def test_outline_is_required_before_draft_generation(client):
    project = create_project(client)
    chapter_response = client.post(
        f"/api/v1/projects/{project['id']}/chapters",
        json={"title": "Orphan Chapter", "summary": "No outline yet."},
    )
    chapter_id = chapter_response.json()["id"]
    response = client.post(
        f"/api/v1/chapters/{chapter_id}/draft:generate",
        json={
            "chapter_goal": "Try to draft anyway",
            "context_window_strategy": "none",
        },
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "outline_required"
    assert "request_id" in body
