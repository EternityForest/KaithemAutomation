"""Hello world entry point for the uv Python container app.

Runs automatically when the app starts.  Keep it UIless: it prints to the
container's stdout, which the app console shows.
"""

import time


def main() -> None:
    print("Hello from the uv Python container app!", flush=True)
    while True:
        time.sleep(60)
        print("still running", flush=True)


if __name__ == "__main__":
    main()
