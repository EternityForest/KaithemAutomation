from pavillion import *
import pavillion

#Make it able to exit faster?
pavillion.daemon = True

import time
import libnacl
if __name__ == '__main__':
    import unittest


    class TestRPC(unittest.TestCase):
        pass

        def test_rpc(self):
            c_pub, c_pk = libnacl.crypto_box_keypair()

            s_pub, s_pk = libnacl.crypto_box_keypair()
            
            cid2 = b'cid2'*4

            #Servers identify clients by client id and key pairs.
            s = Server(pubkeys={cid2:c_pub}, ecc_keypair=(s_pub,s_pk))
            c = Client(keypair=(c_pub,c_pk), serverkey=s_pub, clientID=cid2,cipher=2)

            time.sleep(0.55)
            r= Register("test","foooo")

            s.registers[400] =r

            #Using the "Direct function" method which doesn't have as much introspection capability
            s.registers[401] =lambda c,a: a

            x = c.call(400, b'A test string')

            self.assertEqual(x, b'A test string')

            x = c.call(401, b'A test string')

            self.assertEqual(x, b'A test string')

        def guest_rpc(self):
            s_pub, s_pk = libnacl.crypto_box_keypair()
            
            cid2 = b'cid2'*4

            #Servers identify clients by client id and key pairs.
            #In this case, the server is allowing a guest login from a server it's never heard of.

            #The special value 'guest' tells the client to generate a new keypair.
            s = Server(allow_guest=True, ecc_keypair=(s_pub,s_pk))
            c = Client(keypair='guest', serverkey=s_pub, clientID=cid2,cipher=2)

            time.sleep(0.55)
            r= Register("test","foooo")

            s.registers[400] =r

            #Using the "Direct function" method which doesn't have as much introspection capability
            s.registers[401] =lambda c,a: a

            x = c.call(400, b'A test string')

            self.assertEqual(x, b'A test string')

            x = c.call(401, b'A test string')

            self.assertEqual(x, b'A test string')


    class TestPubsub(unittest.TestCase):

        def test_pubkey_coms(self):
            "Create a client and server, send a message from client to server"
            try:
                c_pub, c_pk = libnacl.crypto_box_keypair()

                s_pub, s_pk = libnacl.crypto_box_keypair()
                
                cid2 = b'cid2'*4

                #Servers identify clients by client id and key pairs.
                s = Server(pubkeys={cid2:c_pub}, ecc_keypair=(s_pub,s_pk))

                detected_subs = []
                class ClientClass(Client):
                    def onNewSubscriber(self, target, addr):
                        detected_subs.append(target)

                self.assertEqual(len(detected_subs),0)                
                c = ClientClass(keypair=(c_pub,c_pk), serverkey=s_pub, clientID=cid2,cipher=2)

                time.sleep(0.5)

                incoming = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = s.messageTarget('TestTarget',z)

                c.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))
                self.assertEqual(len(detected_subs),1)

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                incoming.pop()


                del s
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Assert that the server can be cleaned up by the usual weakref methods
                self.assertEqual(len(incoming),0)

            finally:
                c.close()

        def test_pubkey__reverse_coms(self):
            "Create a client and server, send a message from server to client"
            try:
                c_pub, c_pk = libnacl.crypto_box_keypair()

                s_pub, s_pk = libnacl.crypto_box_keypair()
                
                cid2 = b'cid2'*4

                #Servers identify clients by client id and key pairs.
                s = Server(pubkeys={cid2:c_pub}, ecc_keypair=(s_pub,s_pk))                
                time.sleep(0.5)
                c = Client(keypair=(c_pub,c_pk), serverkey=s_pub, clientID=cid2,cipher=2)

                time.sleep(0.5)

                incoming = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = c.messageTarget('TestTarget',z)

                s.sendMessage("TestTarget","MessageName",b'data_pubkeyreversecoms')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                self.assertEqual(incoming[0],("MessageName",b'data_pubkeyreversecoms',incoming[0][2]))

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                incoming.pop()


                del s
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Assert that the server can be cleaned up by the usual weakref methods
                self.assertEqual(len(incoming),0)

            finally:
                c.close()

        def test_coms(self):
            "Create a client and server, send a message from client to server"
            try:
                psk = b'PSK1'*8
                cid2 = b'cid2'*4

                #Servers identify clients by client id and key pairs.
                s = Server(keys={cid2:psk})
                c = Client(psk=psk, clientID=cid2)

                time.sleep(0.5)

                incoming = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = s.messageTarget('TestTarget',z)

                c.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                incoming.pop()


                del s
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Assert that the server can be cleaned up by the usual weakref methods
                self.assertEqual(len(incoming),0)

            finally:
                c.close()

        def test_conflict(self):
            "Create a client and server, send a message from client to server"
            try:
                psk = b'PSK1'*8
                psk2 = b'PSK2'*8

                cid2 = b'cid2'*4

                #Servers identify clients by client id and key pairs.
                s = Server(keys={cid2:psk})
                
                #This server is also on the default group.
                #It has a different key
                s2 = Server(keys={cid2:psk2})

                c = Client(psk=psk, clientID=cid2)

                time.sleep(0.5)

                incoming = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = s.messageTarget('TestTarget',z)

                c.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))


            finally:
                c.close()


        def test_wrong_client(self):
            "Create a client and server, send a message from client to server"
            try:
                psk = b'PSK1'*8
                cid= b'cid3'*4

                #Servers identify clients by client id and key pairs.
                s = Server(keys={cid:psk})

                wrong_client = Client(psk=b'x'*32, clientID=cid)

                time.sleep(0.5)

                incoming = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = s.messageTarget('TestTarget',z)


                #Assert that a client with the wrong key can't send messages
                self.assertEqual(len(incoming),0)
                wrong_client.sendMessage("TestTarget","MessageName",b'data')
                time.sleep(1)
                self.assertEqual(len(incoming),0)


            finally:
                pass




    class TestMcastPubsub(unittest.TestCase):
        def test_coms(self):
            "Create a client and server, send a message from client to server"
            try:
                psk = b'PSK1'*8
                cid1 = b'cid1'*4

                group = "224.1.0.39"

                #Servers identify clients by client id and key pairs.
                s = Server(keys={cid1:psk},multicast=group)
                c = Client(psk=psk, clientID=cid1,address=(group,1783))
                time.sleep(0.5)

                incoming = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = s.messageTarget('TestTarget',z)

                c.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                incoming.pop()
                self.assertEqual(len(incoming),0)

                del s
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Assert that the server can be cleaned up by the usual weakref methods
                self.assertEqual(len(incoming),0)
                

            finally:
                c.close()

        def test_coms_2servers(self):
            "Create a client and server, send a message from client to server"
            try:
                psk = b'PSK1'*8
                cid1 = b'cid1'*4

                group = "224.1.0.39"
                
                c = Client(psk=psk, clientID=cid1,address=(group,1783))
                time.sleep(0.5)

                #Servers identify clients by client id and key pairs.
                s = Server(keys={cid1:psk},multicast=group)
                s2 = Server(keys={cid1:psk},multicast=group)
                time.sleep(0.3)



                incoming = []
                incoming2 = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = s.messageTarget('TestTarget',z)


                #The ID of the client will be None if the message is sent unsecured.
                def z2(name,data,client):
                    incoming2.append((name,data,client))

                m2 = s2.messageTarget('TestTarget',z2)


                c.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))
                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                self.assertEqual(len(incoming2),1)

                incoming.pop()
                incoming2.pop()

                self.assertEqual(len(incoming),0)
                self.assertEqual(len(incoming2),0)

                del s
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Assert that the server can be cleaned up by the usual weakref methods
                self.assertEqual(len(incoming),0)

                #Deleting one server shouldn't affect the other
                self.assertEqual(len(incoming2),1)

                incoming2.pop()
                self.assertEqual(len(incoming2),0)

                del s2
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Now test deleting the second server
                self.assertEqual(len(incoming2),0)
                

            finally:
                c.close()

        def test_coms_2servers_2clients(self):
            "Create a client and server, send a message from client to server"
            try:
                psk = b'PSK1'*8
                cid1 = b'cid1'*4

                group = "224.1.0.39"

                #Servers identify clients by client id and key pairs.
                s = Server(keys={cid1:psk},multicast=group)
                s2 = Server(keys={cid1:psk},multicast=group)
                time.sleep(0.1)

                c = Client(psk=psk, clientID=cid1,address=(group,1783))
                c2 = Client(psk=psk, clientID=cid1,address=(group,1783))

                time.sleep(0.5)

                incoming = []
                incoming2 = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = s.messageTarget('TestTarget',z)


                #The ID of the client will be None if the message is sent unsecured.
                def z2(name,data,client):
                    incoming2.append((name,data,client))

                m2 = s2.messageTarget('TestTarget',z2)


                c.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")
                while(not incoming2):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")
                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))
                self.assertEqual(incoming2[0],("MessageName",b'data',c.clientID))

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                self.assertEqual(len(incoming2),1)

                incoming.pop()
                incoming2.pop()

                self.assertEqual(len(incoming),0)
                self.assertEqual(len(incoming2),0)



                #Try the same thing but with the other client
                c2.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                while(not incoming2):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))
                self.assertEqual(incoming2[0],("MessageName",b'data',c.clientID))

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                self.assertEqual(len(incoming2),1)

                incoming.pop()
                incoming2.pop()

                self.assertEqual(len(incoming),0)
                self.assertEqual(len(incoming2),0)



                del s
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Assert that the server can be cleaned up by the usual weakref methods
                self.assertEqual(len(incoming),0)

                #Deleting one server shouldn't affect the other
                self.assertEqual(len(incoming2),1)

                incoming2.pop()
                self.assertEqual(len(incoming2),0)

                del s2
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Now test deleting the second server
                self.assertEqual(len(incoming2),0)
                

            finally:
                c.close()

        def test_coms_2servers_2clients_2randomserver_2randomclient(self):
            try:
                psk = b'PSK1'*8
                cid1 = b'cid1'*4
                cid2 = b'cid2'*4

                psk2 = b'PSK2'*8


                group = "224.1.0.39"

                #Servers identify clients by client id and key pairs.
                s = Server(keys={cid1:psk},multicast=group)
                s2 = Server(keys={cid1:psk},multicast=group)

                #interfering servers
                s3 = Server(keys={cid1:psk2},multicast=group)
                s4 = Server(keys={cid2:psk2},multicast=group)
                time.sleep(0.1)


                c = Client(psk=psk, clientID=cid1,address=(group,1783))
                c2 = Client(psk=psk, clientID=cid1,address=(group,1783))

                #interfering clients
                c3 = Client(psk=psk2, clientID=cid1,address=(group,1783))
                c4 = Client(psk=psk, clientID=cid2,address=(group,1783))

                time.sleep(0.5)

                incoming = []
                incoming2 = []

                #The ID of the client will be None if the message is sent unsecured.
                def z(name,data,client):
                    incoming.append((name,data,client))

                m = s.messageTarget('TestTarget',z)


                #The ID of the client will be None if the message is sent unsecured.
                def z2(name,data,client):
                    incoming2.append((name,data,client))

                m2 = s2.messageTarget('TestTarget',z2)


                c.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                while(not incoming2):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))
                self.assertEqual(incoming2[0],("MessageName",b'data',c.clientID))

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                self.assertEqual(len(incoming2),1)

                incoming.pop()
                incoming2.pop()

                self.assertEqual(len(incoming),0)
                self.assertEqual(len(incoming2),0)



                #Try the same thing but with the other server
                c2.sendMessage("TestTarget","MessageName",b'data')
                
                start = time.time()
                while(not incoming):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")

                while(not incoming2):
                    time.sleep(0.1)
                    if start<time.time()-5:
                        raise RuntimeError("Timed Out")
                self.assertEqual(incoming[0],("MessageName",b'data',c.clientID))
                self.assertEqual(incoming2[0],("MessageName",b'data',c.clientID))

                #Assert once and only once
                self.assertEqual(len(incoming),1)
                self.assertEqual(len(incoming2),1)

                incoming.pop()
                incoming2.pop()

                self.assertEqual(len(incoming),0)
                self.assertEqual(len(incoming2),0)



                del s
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Assert that the server can be cleaned up by the usual weakref methods
                self.assertEqual(len(incoming),0)

                #Deleting one server shouldn't affect the other
                self.assertEqual(len(incoming2),1)

                incoming2.pop()
                self.assertEqual(len(incoming2),0)

                del s2
                time.sleep(1)
                c.sendMessage("TestTarget","MessageName",b'data')

                #Now test deleting the second server
                self.assertEqual(len(incoming2),0)
                

            finally:
                c.close()
    unittest.main()
