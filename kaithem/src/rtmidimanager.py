
from src import tagpoints
from scullery import messagebus
from src import scheduling
import traceback

allInputs = {}

tagPoints={}





def setTag(n,v,a=None):
    if not n in tagPoints:
        tagPoints[n]=tagpoints.Tag(n)
        tagPoints[n].min=0
        tagPoints[n].max=127
    tagPoints[n].setClaimVal('default',v,timestamp=None,annotation=None)

def setTag14(n,v,a=None):
    if not n in tagPoints:
        tagPoints[n]=tagpoints.Tag(n)
        tagPoints[n].min=0
        tagPoints[n].max=16383
    tagPoints[n].setClaimVal('default',v,timestamp=None,annotation=None)

def onMidiMessage(m,d):
    if m.isNoteOn():
        messagebus.postMessage("/midi/"+d,('noteon', m.getChannel(),m.getNoteNumber(),m.getVelocity()) )
        setTag("/midi/"+d+"/"+str(m.getChannel())+".note", m.getNoteNumber(), a= m.getVelocity())

    elif m.isNoteOff():
        messagebus.postMessage("/midi/"+d,('noteoff', m.getChannel(),m.getNoteNumber()))
        setTag("/midi/"+d+"/"+str(m.getChannel())+".note", 0, a= 0)

    elif m.isController():
        messagebus.postMessage("/midi/"+d, ('cc', m.getChannel(),m.getControllerNumber(),m.getControllerValue()))
        setTag("/midi/"+d+"/"+str(m.getChannel())+".cc["+str(m.getControllerNumber())+']', m.getControllerValue(), a= 0)

    elif m.isPitchWheel():
        messagebus.postMessage("/midi/"+d, ('pitch', m.getChannel(),m.getPitchWheelValue()))
        setTag14("/midi/"+d+"/"+str(m.getChannel())+".pitch", m.getPitchWheelValue(), a= 0)


once =[0]


def doScan():
    try:
        import rtmidi
    except ImportError:
        if once[0] == 0:
            messagebus.postMessage("/system/notifications/errors/","python-rtmidi is missing. Most MIDI related features will not work.")
            once[0]=1
        return


    m=rtmidi.RtMidiIn()
    torm =[]

    present =[(i,m.getPortName(i)) for i in range(m.getPortCount())]

    for i in allInputs:
        if not i in present:
            torm.append(i)
    for i in torm:
        del allInputs[i]


    for i in present:
        if not i in allInputs:
            try:
                m=rtmidi.RtMidiIn()
                m.openPort(i[0])
                def f(x,d=i[1].replace(":",'_').replace("[",'').replace("]",'').replace(" ",'') ):
                    try:
                        onMidiMessage(x,d)
                    except:
                        print(traceback.format_exc())
                m.setCallback(f)
                allInputs[i]=(m,f)
            except:
                print("Can't use MIDI:"+str(i))


s = scheduling.RepeatingEvent(doScan, 10)
s.schedule()



