import sys,os
sys.path.append(os.path.join(sys.path[0],'..','..','thirdparty'))

if sys.version_info < (3,0):
    sys.path.append(os.path.join(sys.path[0],'..','..','thirdparty',"python2"))
    from gzip import open as opengzip
else:
    from gzip import GzipFile as opengzip
    sys.path.append(os.path.join(sys.path[0],'..','..','thirdparty',"python3"))
    
import TestMessageBus
import testevents
import testunitconversions

import testmodulesystem
