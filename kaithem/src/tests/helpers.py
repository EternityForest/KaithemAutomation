from kaithem.src import quart_app


async def make_client():
    client = quart_app.app.test_client(use_cookies=True)
    x = await client.post(
        "/login/login",
        follow_redirects=True,
        form={
            "username": "admin",  # pragma: allowlist secret
            "password": "test-admin-password",  # pragma: allowlist secret
        },  # pragma: allowlist secret
    )  # pragma: allowlist secret

    assert x.status_code == 200
    return client
