import pytest

from kaithem.src import quart_app


@pytest.mark.asyncio
async def test_app():
    client = quart_app.app.test_client()

    await client.post("/login", data={"username": "testuser", "password": "testpass"})  # pragma: allowlist secret
    response = await client.get("/")
    assert response.status_code == 200

    response = await client.get("/tagpoints")
    assert response.status_code == 200

    response = await client.get("/about")
    assert response.status_code == 200
