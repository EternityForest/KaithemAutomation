import os
import terminado

from . import kaithemobj, directories


bashrc = os.path.join(directories.vardir, 'core.settings/bashrc.sh')
os.makedirs(os.path.join(directories.vardir, 'core.settings'), exist_ok=True)

if not os.path.exists(bashrc):
    with open(bashrc, 'w') as f:
        with open(os.path.join(directories.datadir, 'default_bashrc.sh')) as f2:
            f.write(f2.read())


bashrc = os.path.join(directories.vardir, 'core.settings/bashrc.sh')

term_manager = terminado.UniqueTermManager(shell_command=["bash", '--rcfile', bashrc])

kaithemobj.kaithem.web.add_tornado_app("/web_console_ws.*", terminado.TermSocket, {"term_manager": term_manager})