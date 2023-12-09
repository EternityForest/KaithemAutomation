import sys
DEBUG = False
if '--debug' in sys.argv:
    DEBUG = True
    sys.argv.remove('--debug')

CLIENT_DIR = 'src'
