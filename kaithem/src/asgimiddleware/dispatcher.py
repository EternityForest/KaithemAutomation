import traceback

import starlette.responses

from kaithem.src import pages


class AsgiDispatcher:
    def __init__(self, patterns):
        self.patterns = []
        for i in patterns:
            self.patterns.append((i, patterns[i]))

        # Longest to shortest
        self.patterns.sort()
        self.patterns.reverse()

    async def __call__(self, scope, receive, send):
        app = None
        for p in self.patterns:
            scope_path = p[0]
            asgi_application = p[1]

            if scope["path"].startswith(scope_path):
                app = asgi_application
                break

        assert app
        try:
            await app(scope, receive, send)
        except pages.KaithemUserPermissionError:
            if scope["type"] == "http":
                return pages.loginredirect(scope["path"])
            else:
                raise
        except Exception:
            if scope["type"] == "http":
                r = starlette.responses.Response(
                    pages.get_template("errors/e500.html").render(
                        e=traceback.format_exc()
                    )
                )
                await r(scope, receive, send)
            else:
                print("Error", traceback.format_exc())
            raise
