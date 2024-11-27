from kaithem.src import quart_app


async def make_client():
    client = quart_app.app.test_client()
    await client.post(
        "/login",
        data={
            "username": "testuser",  # pragma: allowlist secret
            "password": "testpass",  # pragma: allowlist secret
        },  # pragma: allowlist secret
    )  # pragma: allowlist secret
