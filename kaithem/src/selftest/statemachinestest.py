# SPDX-FileCopyrightText: Copyright 2019 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# This file runs a self test when python starts


def stateMachinesTest():
    import time

    from scullery import statemachines

    class m(dict):
        pass

    module = m()

    blink = statemachines.StateMachine(start="off")

    on = blink.add_state("on")
    off = blink.add_state("off")

    blink.set_timer("on", 0.5, "off")

    blink.set_timer("off", 0.5, "on")
    blink.add_rule("off", "begin", "on")
    blink("begin")
    module["Oscillating State Machine"] = blink

    module.sm_lamp = 0

    def on():
        module.sm_lamp = 1

    def off():
        module.sm_lamp = 0

    sm = statemachines.StateMachine(start="off")

    on = sm.add_state("on", enter=on)
    off = sm.add_state("off", enter=off)

    sm.set_timer("on", 0.5, "off")

    sm.add_rule("off", "motion", "on")

    if module.sm_lamp:
        raise RuntimeError("state machine imaginary lamp is on too soon")
    sm.event("motion")
    time.sleep(0.2)
    if not module.sm_lamp:
        raise RuntimeError("state machine imaginary lamp is not on")
    time.sleep(1)

    if module.sm_lamp:
        raise RuntimeError("state machine imaginary lamp didn't turn itself off within 1s")

    # Turn it on before deleting so we can make sure the timer won't trigger after it's gone
    sm.event("motion")
    del sm

    sm = statemachines.StateMachine(start="off")

    on = sm.add_state("on", enter=on)
    off = sm.add_state("off", enter=off)

    lightsOff = [False]

    lastPoll = [0]

    # Polled function trigger, when f returns true
    # We should go to the next state
    def f():
        lastPoll[0] = time.time()
        return lightsOff[0]

    sm.add_rule("on", f, "off")
    sm.add_rule("off", "motion", "on")

    if not sm.state == "off":
        raise RuntimeError("Unexpected state")

    sm.event("motion")
    if not sm.state == "on":
        raise RuntimeError("Unexpected state")

    # Make sure polling doesn't trigger it if false
    time.sleep(0.3)
    if not sm.state == "on":
        raise RuntimeError("Unexpected state")

    lightsOff[0] = True
    time.sleep(0.3)

    if not sm.state == "off":
        raise RuntimeError("Unexpected state")

    t = lastPoll[0]
    if not t:
        raise RuntimeError("Test probably is buggy")

    time.sleep(0.3)
    if not lastPoll[0] == t:
        raise RuntimeError("State machine continued polling after exiting event")

    lightsOff[0] = False
    time.sleep(0.25)
    t = lastPoll[0]
    del sm
    time.sleep(1)

    if not lastPoll[0] == t:
        raise RuntimeError("State machine continued polling after deleting")

    transitions = []

    sm = statemachines.StateMachine(start="off")

    on = sm.add_state("on", enter=on)
    off = sm.add_state("off", enter=off)
    sm.add_rule("off", "switch", "on")

    def subscriber(s):
        transitions.append(s)

    sm.subscribe(subscriber)
    sm.event("switch")
    if not transitions == ["on"]:
        print(transitions)
        raise RuntimeError("State machines not working as they should")
