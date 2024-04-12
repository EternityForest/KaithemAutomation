# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import os
import subprocess
import time

import terminado

from kaithem.src import directories, kaithemobj, pages, settings, util

bashrc = os.path.join(directories.vardir, "core.settings/bashrc.sh")
os.makedirs(os.path.join(directories.vardir, "core.settings"), exist_ok=True)

if not os.path.exists(bashrc):
    with open(bashrc, "w") as f:
        with open(os.path.join(directories.datadir, "default_bashrc.sh")) as f2:
            f.write(f2.read())


bashrc = os.path.join(directories.vardir, "core.settings/bashrc.sh")

term_manager = terminado.UniqueTermManager(shell_command=["bash", "--rcfile", bashrc])

kaithemobj.kaithem.web.add_tornado_app("/web_console_ws.*", terminado.TermSocket, {"term_manager": term_manager})


td = os.path.join(os.path.dirname(__file__), "html", "console.html")


class Page(settings.PagePlugin):
    def handle(self, **kwargs):
        if "script" in kwargs:
            pages.postOnly()
            x = ""
            env = {}
            env.update(os.environ)

            if util.which("bash"):
                p = subprocess.Popen(
                    "bash -i",
                    universal_newlines=True,
                    shell=True,
                    env=env,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            else:
                p = subprocess.Popen(
                    "sh -i",
                    universal_newlines=True,
                    shell=True,
                    env=env,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            t = p.communicate(kwargs["script"])

            if isinstance(t, bytes):
                try:
                    t = t.decode("utf-8")
                except Exception:
                    pass

            x += t[0] + t[1]
            try:
                time.sleep(0.1)
                t = p.communicate("")
                x += t[0] + t[1]
                p.kill()
                if p.stdout:
                    p.stdout.close()
                if p.stderr:
                    p.stderr.close()
                if p.stdin:
                    p.stdin.close()
            except Exception:
                pass
            return pages.get_template(td).render(output=x)

        else:
            return pages.get_template(td).render(output="Kaithem System Shell")


p = Page("console", ("system_admin",), title="System Shell")
