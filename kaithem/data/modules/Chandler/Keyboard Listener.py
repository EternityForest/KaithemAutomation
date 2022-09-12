## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1662981829353834
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    mapping = {
    
        'up':"ArrowUp",
        'down': "ArrowDown",
        'left': "ArrowLeft",
        'right': "ArrowRight",
        'backspace': "Backspace",
        "ctrl_l": "Control",
        "ctrl_r": "Control",
        "shift_l": 'Shift',
        "shift_r": 'Shift',
    
        'tab': "Tab",
        'end':"End",
        'page_up':"PageUp",
        'page_down':"PageDown",
        'home': "Home",
        'enter': "Enter"
    
    }
    from pynput import keyboard
    
    def on_press(key):    
        try:
            kaithem.chandler.event("serverkeydown."+key.char)
        except AttributeError:
            x = str(key).split('.')[-1]
            if x in mapping:
                x = mapping[x]
            kaithem.chandler.event("serverkeydown."+x)
    
        
    
    def on_release(key):    
        try:
            kaithem.chandler.event("serverkeyup."+key.char)
        except AttributeError:
            x = str(key).split('.')[-1]
            if x in mapping:
                x = mapping[x]
            kaithem.chandler.event("serverkeyup."+x)
    
    
    # ...or, in a non-blocking fashion:
    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release)
    listener.start()
    
    
    def __del__():
        listener.stop()

def eventAction():
    pass
