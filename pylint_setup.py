import os,sys
sys.path = [os.path.join(os.path.dirname(__file__),"kaithem")] + sys.path
from src import pathsetup
pathsetup.setupPath(force_local=True)