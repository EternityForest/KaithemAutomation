import pytest

from .helpers import make_client


@pytest.mark.asyncio
async def test_app():
    client = await make_client()

    response = await client.get("/")
    assert response.status_code == 200

    response = await client.get("/tagpoints")
    assert response.status_code == 200

    response = await client.get("/about")
    assert response.status_code == 200
