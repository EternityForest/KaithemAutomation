from common import fail,suceed
from messagebus import *
import  messagebus

tester = {}

def test():
    FAIL = False
    def dostuff():
        def dummy(a,b):
            pass
        time.sleep(random.random()/100)
        subscribe('a',dummy)
        postMessage('a','poopoo')
        del dummy
    
    def datatest():
        i = str(os.urandom(10)).replace('/','|')
        def recive(x,y):
            tester[x] = y
        
        subscribe(i,recive)
        x =str(os.urandom(100))
        postMessage(i,x)
        time.sleep((random.random()/100)+0.05)
        if not tester[i] == x:
            fail('Message not properly recieved')
        else:
            pass
            
    def datatest2():
        i = 'potty/'+str(os.urandom(10)).replace('/','|')
        def recive(x,y):
            tester[x] = y
        
        subscribe('potty/',recive)
        x =str(os.urandom(100))
        postMessage(i,x)
        time.sleep((random.random()/100)+0.05)
        if not tester[i] == x:
            fail('Message not properly recieved.')
        else:
            #print("hooray")
            pass
    
    for i in range(0,1):
        for i in range(0,100):
            t = threading.Thread(target=dostuff)
            t.start()
            t = threading.Thread(target=datatest)
            t.start()
            t = threading.Thread(target=datatest2)
            t.start()
            time.sleep(0.05)    
   
if len(messagebus._bus.subscribers) > 5:
    fail('It appears that there are old subscriptions in the list for deleted callbacks. Memory Leak!')
    
suceed("Sucess in testing Message Bus system")