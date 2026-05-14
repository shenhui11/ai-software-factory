import pytest
from fastapi import status
from httpx import AsyncClient

from tests.conftest import SyncASGIClient


def make_project_payload() -> dict[str, object]:
    return {
        "title": "Async Chronicle",
        "genre": "fantasy",
        "length_type": "long",
        "template_id": "",
        "summary": "Hero rebuilds a broken kingdom.",
        "character_cards": ["Hero", "Rival"],
        "world_rules": ["Magic has a price"],
        "event_summary": ["The city fell in chapter zero"],
        "mode_default": "manual",
    }


class TestAsyncApi:
    async def _auth_headers(self, async_client: AsyncClient, username: str) -> dict[str, str]:
        await async_client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret123", "role": "creator"},
        )
        logged_in = await async_client.post(
            "/api/auth/login",
            json={"username": username, "password": "secret123"},
        )
        token = logged_in.json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.anyio
    async def test_register_login_and_me(self, async_client: AsyncClient) -> None:
        registered = await async_client.post(
            "/api/auth/register",
            json={"username": "async_creator", "password": "secret123", "role": "creator"},
        )
        assert registered.status_code == status.HTTP_200_OK

        logged_in = await async_client.post(
            "/api/auth/login",
            json={"username": "async_creator", "password": "secret123"},
        )
        assert logged_in.status_code == status.HTTP_200_OK
        token = logged_in.json()["data"]["token"]

        me = await async_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == status.HTTP_200_OK
        assert me.json()["data"]["username"] == "async_creator"

    @pytest.mark.anyio
    async def test_create_project_and_fetch_detail(self, async_client: AsyncClient) -> None:
        headers = await self._auth_headers(async_client, "async_project_creator")
        created = await async_client.post("/api/projects", json=make_project_payload(), headers=headers)
        assert created.status_code == status.HTTP_200_OK
        project_id = created.json()["data"]["id"]

        detail = await async_client.get(f"/api/projects/{project_id}", headers=headers)
        assert detail.status_code == status.HTTP_200_OK
        body = detail.json()["data"]
        assert body["project"]["title"] == "Async Chronicle"
        assert body["copyright_notice"]

    @pytest.mark.anyio
    @pytest.mark.integration
    async def test_generate_task_async_flow(self, async_client: AsyncClient) -> None:
        headers = await self._auth_headers(async_client, "async_task_creator")
        created = await async_client.post("/api/projects", json=make_project_payload(), headers=headers)
        project_id = created.json()["data"]["id"]

        task_response = await async_client.post(
            f"/api/projects/{project_id}/chapters/generate",
            json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
            headers=headers,
        )
        assert task_response.status_code == status.HTTP_200_OK
        task_id = task_response.json()["data"]["id"]

        run_response = await async_client.post(f"/api/projects/{project_id}/tasks/{task_id}/run", headers=headers)
        assert run_response.status_code == status.HTTP_200_OK

        detail = await async_client.get(f"/api/projects/{project_id}/tasks/{task_id}", headers=headers)
        assert detail.status_code == status.HTTP_200_OK
        chapter = detail.json()["data"]["chapters"][0]
        assert len(chapter["outline_options"]) == 3
        assert chapter["drafts"]

    def test_delete_chapter_sync(self, test_client) -> None:
        client = SyncASGIClient(test_client._app)
        client.post(
            "/api/auth/register",
            json={"username": "delete_creator", "password": "secret123", "role": "creator"},
        )
        logged_in = client.post(
            "/api/auth/login",
            json={"username": "delete_creator", "password": "secret123"},
        )
        token = logged_in.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post("/api/projects", json=make_project_payload(), headers=headers)
        project_id = created.json()["data"]["id"]

        task_response = client.post(
            f"/api/projects/{project_id}/chapters/generate",
            json={"mode": "manual", "chapter_count": 1, "start_chapter_index": 1},
            headers=headers,
        )
        task_id = task_response.json()["data"]["id"]

        run_response = client.post(f"/api/projects/{project_id}/tasks/{task_id}/run", headers=headers)
        assert run_response.status_code == status.HTTP_200_OK

        detail = client.get(f"/api/projects/{project_id}/tasks/{task_id}", headers=headers)
        chapter_id = detail.json()["data"]["chapters"][0]["id"]

        deleted = client.request("DELETE", f"/api/projects/{project_id}/chapters/{chapter_id}", headers=headers)
        assert deleted.status_code == status.HTTP_200_OK
        assert deleted.json()["data"]["project"]["chapters"] == []

    def test_admin_can_list_users_sync(self, test_client) -> None:
        client = SyncASGIClient(test_client._app)
        client.post(
            "/api/auth/register",
            json={"username": "quota_target_user", "password": "secret123", "role": "creator"},
        )
        client.post(
            "/api/auth/register",
            json={"username": "quota_admin_user", "password": "secret123", "role": "admin"},
        )
        logged_in = client.post(
            "/api/auth/login",
            json={"username": "quota_admin_user", "password": "secret123"},
        )
        token = logged_in.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}", "X-User-Role": "admin"}

        response = client.get("/admin/users", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        users = response.json()["data"]
        assert any(user["username"] == "quota_target_user" for user in users)
