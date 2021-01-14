## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: true, disabled: false, enable: true, once: true, priority: interactive,
  rate-limit: 2.5, resource-timestamp: 1610593270905970, resource-type: event}

"""

__trigger__='True'

if __name__=='__setup__':
    import time, random
    module.span = kaithem.widget.DynamicSpan()
    module.button = kaithem.widget.Button()
    
    def f(user,value):
        if 'pushed' in value:
            module.span.write("Button Last Pushed at Timestamp: "+str(time.time()))
            
    module.button.attach(f)
    module.span.write("Button not pressed")
    
    module.timewidget = kaithem.widget.TimeWidget()
    
    module.meter = kaithem.widget.Meter(high_warn=70,high=80)
    module.slider = kaithem.widget.Slider(min=0,max=255,step=1)
    module.switch = kaithem.widget.Switch()
    module.switchspan = kaithem.widget.DynamicSpan()
    
    def f(usr,value):
        module.switchspan.write(str(value))
        raise RuntimeError("This is a test error")
        
    module.switch.attach(f)
    
    
    module.mass= []
    for i in range(0,24):
        module.mass.append(kaithem.widget.Slider(min=0,max=255,step=1))
    module.textdisplay = kaithem.widget.TextDisplay()
    module.textdisplay.write(kaithem.misc.lorem())
    
    module.scroll = kaithem.widget.ScrollingWindow()

def eventAction():
    module.meter.write(random.random()*100)
    module.textdisplay.write(kaithem.misc.lorem())
    module.scroll.write(kaithem.misc.lorem())
