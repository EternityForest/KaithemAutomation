# import os
# import subprocess
# import threading
# import time
# import asyncio
# import niquests


# def test_run_playwright():
#     # This causes problems if imported before the app is initialized
#     from kaithem.src import auth  # noqa
#     import kaithem

#     auth.add_user("admin", "test-admin-password")
#     auth.add_user_to_group("admin", "Administrators")

#     def f():
#         for i in range(25):
#             r = niquests.get("https://127.0.0.1:8002")
#             if r.status_code == 200:
#                 break
#             time.sleep(1)
#         r = niquests.get("https://127.0.0.1:8002")
#         assert r.status_code == 200

#         subprocess.check_output("npx playwright test", shell=True, stderr=subprocess.STDOUT)
#         subprocess.check_output(["kill", str(os.getpid())], stderr=subprocess.STDOUT)

#     t = threading.Thread(target=f)
#     t.start()

#     kaithem.start_server()

