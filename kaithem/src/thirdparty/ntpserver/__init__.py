
#This version of the code was largely sourced from a fork at
#https://github.com/cillian64/ntpserver/blob/master/ntpserver.py
#But has been modified a fair amount.

import socket
import time
import threading
import select
import sys
import ntplib
import logging

logger = logging.getLogger("ntpserver")

if sys.version_info[0] == 2:
    import Queue as queue
else:
    import queue


class RecvThread(threading.Thread):
    def __init__(self, sock, taskQueue):
        threading.Thread.__init__(self)
        self.sock = sock
        self.taskQueue = taskQueue

    def run(self):
        while True:
            rlist, wlist, elist = select.select([self.sock], [], [], 1)
            if len(rlist) != 0:
                for tempSocket in rlist:
                    try:
                        data, addr = tempSocket.recvfrom(1024)
                        recvTimestamp = ntplib.system_to_ntp_time(time.time())
                        self.taskQueue.put((data, addr, recvTimestamp))
                    except socket.error as msg:
                        logging.exception("Error in NTP server")


class WorkThread(threading.Thread):
    def __init__(self, sock, taskQueue):
        threading.Thread.__init__(self)
        self.sock = sock
        self.taskQueue = taskQueue

    def run(self):
        while True:
            try:
                data, addr, recvTimestamp = self.taskQueue.get(timeout=1)
                recvPacket = ntplib.NTPPacket()
                recvPacket.from_data(data)
                timeStamp_high = ntplib._to_int(recvPacket.tx_timestamp)
                timeStamp_low = ntplib._to_frac(recvPacket.tx_timestamp)
                sendPacket = ntplib.NTPPacket(version=3, mode=4)
                sendPacket.stratum = 2
                sendPacket.poll = 10
                '''
                sendPacket.precision = 0xfa
                sendPacket.root_delay = 0x0bfa
                sendPacket.root_dispersion = 0x0aa7
                sendPacket.ref_id = 0x808a8c2c
                '''
                sendPacket.ref_timestamp = recvTimestamp-5
                sendPacket.orig_timestamp = ntplib._to_time(timeStamp_high,
                                                            timeStamp_low)
                sendPacket.recv_timestamp = recvTimestamp
                sendPacket.tx_timestamp = ntplib.system_to_ntp_time(
                        time.time())
                self.sock.sendto(sendPacket.to_data(), addr)
            except queue.Empty:
                continue



def runServer(addr = "0.0.0.0", port=123):
    global RecvThread
    global WorkThread
    taskQueue = queue.Queue()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((addr, port))
    print("NTP listening on local socket: ", sock.getsockname())
    recvThread = RecvThread(sock, taskQueue)
    recvThread.daemon = True
    recvThread.start()
    workThread = WorkThread(sock, taskQueue)
    workThread.daemon = True
    workThread.start()
    return sock.getsockname()

if __name__ == "__main__":
    while True:
        try:
            runServer()
            time.sleep(0.5)
        except KeyboardInterrupt:
            break
        
