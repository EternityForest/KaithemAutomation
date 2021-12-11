# Copyright (c) 2018-2020 Terry Greeniaus.
'''
pyreap - Ensure your subprocesses are terminated when you die instead of being
         reparented to init.
'''
import subprocess
import signal
import errno
import sys
import os


# We export only the Popen() function.
__all__ = ['Popen']


# Record the path to reap.py before somebody chdirs us.
REAP_PATH = os.path.realpath(__file__)

# The parent PID we were spawned with.  Only valid in sub_reap().
PARENT_PID = None

# The child process we spawned from sub_reap().
CHILD_PROC = None


def Popen(args, **kwargs):
    '''
    Works similarly to Popen.  This will execute reap.py as a standalone script
    in a subprocess, and that sub-reap.py will then execute your desired
    command in another subprocess.  Sub-reap.py will periodically check for
    either a dead child or a new parent PID and either kill itself or kill the
    child as necessary.
    '''
    # Execute ourselves as a sub-process.
    cmd = ['/usr/bin/env', 'python3', REAP_PATH, '%s' % os.getpid()] + args
    return subprocess.Popen(cmd, **kwargs)


def sigalrm(_signum, _frame):
    '''
    Check if our parent PID no longer matches and kill the child if that's the
    case.  If we end up killing the child, we'll later get a SIGCHLD and clean
    ourselves up too.
    '''
    if os.getppid() != PARENT_PID:
        CHILD_PROC.kill()
    else:
        signal.alarm(1)


def sigterm(_signum, _frame):
    '''
    We've received a terminate signal.  Kill the child and then wait for
    SIGCHLD to clean up.
    '''
    CHILD_PROC.kill()


def sub_reap(args):
    '''
    usage: reap.py parent_pid cmd [args...]

    We spawn the child and then install a SIGALRM handler to periodically check
    for a new parent_pid.  Using signals avoids race conditions.  Finally, we
    os.wait() until the subprocess terminates.
    '''
    global PARENT_PID
    global CHILD_PROC

    PARENT_PID = int(args[1])
    signal.signal(signal.SIGALRM, sigalrm)
    signal.signal(signal.SIGTERM, sigterm)
    CHILD_PROC = subprocess.Popen(args[2:], close_fds=False)
    signal.alarm(1)

    while True:
        try:
            _, status = os.wait()
            break
        except OSError as e:
            if e.errno != errno.EINTR:
                os._exit(1)
        except KeyboardInterrupt:
            pass

    if (status & 0xFF) == 0:
        os._exit(status >> 8)
    os._exit(0x80 | (status & 0xFF))


if __name__ == '__main__':
    sub_reap(sys.argv)
