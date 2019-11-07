#Copyright Daniel Dunn 2019
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

#This file runs a self test when python starts



def stateMachinesTest():
    import time
    from .. import statemachines
    class m(dict):
        pass
    module=m()
        
    blink = statemachines.StateMachine(start="off")

    on = blink.addState("on")
    off = blink.addState("off")

    blink.setTimer("on", 1, "off")

    blink.setTimer("off", 1, "on")
    blink.addRule("off", 'begin', "on")
    blink('begin')
    module['Oscillating State Machine'] = blink


    blah =statemachines.StateMachine(start="test")
    blah.addState("test")
    blah.addState("test2")
    blah.goto("test2")

    blah2 = statemachines.StateMachine(start="test")
    blah.addState("test")
    blah.addState("test2")

    blah.handoff(blah2)

    if not blah2.state =="test2":
        raise RuntimeError("State was not correctly transferred to new machine")
                
    if not blah2.prevState =="test":
        raise RuntimeError("previous state was not correctly transferred to new machine")
        
    if not blah2.enteredState ==blah.enteredState:
        raise RuntimeError("previous state entry time was not correctly transferred to new machine")
                            



    module.sm_lamp = 0

    def on():
        module.sm_lamp = 1
        
    def off():
        module.sm_lamp = 0
        
    sm = statemachines.StateMachine(start="off")

    on = sm.addState("on", enter=on)
    off = sm.addState("off", enter=off)

    sm.setTimer("on", 1, "off")

    sm.addRule('off', "motion","on")

    if module.sm_lamp:
        raise RuntimeError("state machine imaginary lamp is on too soon")
    sm.event("motion")
    time.sleep(0.3)
    if not module.sm_lamp:
        raise RuntimeError("state machine imaginary lamp is not on")
    time.sleep(2)

    if module.sm_lamp:
        time.sleep(8)
        if module.sm_lamp:
            raise RuntimeError("state machine imaginary lamp didn't turn itself off within 10s")
        else:
            raise RuntimeError("state machine imaginary lamp didn't turn itself off within 2s")

    #Turn it on before deleting so we can make sure the timer won't trigger after it's gone
    sm.event('motion')
    del sm

    sm = statemachines.StateMachine(start="off")

    on = sm.addState("on", enter=on)
    off = sm.addState("off", enter=off)

    lightsOff = [False]

    lastPoll = [0]

    #Polled function trigger, when f returns true
    #We should go to the next state
    def f():
        lastPoll[0]=time.time()
        return lightsOff[0]

    sm.addRule('on', f, "off")
    sm.addRule('off', "motion","on")

    if not sm.state=='off':
        raise RuntimeError("Unexpected state")

       
    sm.event("motion")
    if not sm.state=='on':
        raise RuntimeError("Unexpected state")
        
    #Make sure polling doesn't trigger it if false
    time.sleep(0.3)
    if not sm.state=='on':
        raise RuntimeError("Unexpected state")

    lightsOff[0]=True
    time.sleep(0.3)

    if not sm.state=='off':
        raise RuntimeError("Unexpected state")

    t = lastPoll[0]
    if not t:
        raise RuntimeError("Test probably is buggy")

    time.sleep(0.3)
    if not lastPoll[0]==t:
        raise RuntimeError("State machine continued polling after exiting event")

    lightsOff[0]=False
    time.sleep(0.25)
    t=lastPoll[0]
    del sm
    time.sleep(1)

    if not lastPoll[0]==t:
            raise RuntimeError("State machine continued polling after deleting")

    
    transitions =[]

    sm = statemachines.StateMachine(start="off")

    on = sm.addState("on", enter=on)
    off = sm.addState("off", enter=off)
    sm.addRule('off','switch','on')

    def subscriber(s):
        transitions.append(s)
    sm.subscribe(subscriber)
    sm.event('switch')
    if not transitions==['on']:
        print(transitions)
        raise RuntimeError("State machines not working as they should")