## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1651714038078631, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    
    
    def listRtmidi():
        try:
            import rtmidi
        except ImportError:
            if once[0] == 0:
                messagebus.postMessage("/system/notifications/errors/","python-rtmidi is missing. Most MIDI related features will not work.")
                once[0]=1
            return []
    
        m=rtmidi.RtMidiIn()
    
        return [(m.getPortName(i)) for i in range(m.getPortCount())]
    
    module.listRtmidi = listRtmidi
    
    
    from src import tagpoints
    def limitedTagsListing():
        #Make a list of all the tags,
        #Unless there's way too many
        #Then only list some of them
    
        limitedTagsListing=[]
        for i in tagpoints.allTagsAtomic:
            if len(limitedTagsListing)>1024:
                break
            limitedTagsListing.append(i)
        return limitedTagsListing
    
    module.limitedTagsListing=limitedTagsListing
    
    
    
    def commandTagsListing():
        #Make a list of all the tags,
        #Unless there's way too many
        #Then only list some of them
    
        limitedTagsListing=[]
        t =  tagpoints.allTagsAtomic
        for i in t:
            x = t[i]()
            if x.subtype =='event':
                if len(limitedTagsListing)>250:
                    break
                limitedTagsListing.append(i)
        return limitedTagsListing
    
    module.commandTagsListing=commandTagsListing

def eventAction():
    pass
