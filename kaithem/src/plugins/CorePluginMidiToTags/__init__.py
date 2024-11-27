# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import traceback

from scullery import messagebus, scheduling

from kaithem.src import tagpoints

allInputs = {}

tagPoints = {}


def setTag(n, v, a=None):
    if n not in tagPoints:
        tagPoints[n] = tagpoints.Tag(n)
        tagPoints[n].min = 0
        tagPoints[n].max = 127
    tagPoints[n].set_claim_val("default", v, timestamp=None, annotation=None)


def setTag14(n, v, a=None):
    if n not in tagPoints:
        tagPoints[n] = tagpoints.Tag(n)
        tagPoints[n].min = 0
        tagPoints[n].max = 16383
    tagPoints[n].set_claim_val("default", v, timestamp=None, annotation=None)


def onMidiMessage(m, d):
    if m.isNoteOn():
        messagebus.post_message(
            f"/midi/{d}",
            ("noteon", m.getChannel(), m.getNoteNumber(), m.getVelocity()),
        )
        setTag(
            f"/midi/{d}/{str(m.getChannel())}.note",
            m.getNoteNumber(),
            a=m.getVelocity(),
        )

    elif m.isNoteOff():
        messagebus.post_message(
            f"/midi/{d}", ("noteoff", m.getChannel(), m.getNoteNumber())
        )
        setTag(f"/midi/{d}/{str(m.getChannel())}.note", 0, a=0)

    elif m.isController():
        messagebus.post_message(
            f"/midi/{d}",
            (
                "cc",
                m.getChannel(),
                m.getControllerNumber(),
                m.getControllerValue(),
            ),
        )
        setTag(
            f"/midi/{d}/{str(m.getChannel())}.cc.{str(m.getControllerNumber())}",
            m.getControllerValue(),
            a=0,
        )

    elif m.isPitchWheel():
        messagebus.post_message(
            f"/midi/{d}", ("pitch", m.getChannel(), m.getPitchWheelValue())
        )
        setTag14(
            f"/midi/{d}/{str(m.getChannel())}.pitch",
            m.getPitchWheelValue(),
            a=0,
        )


def normalize_midi_name(t):
    t = (
        t.lower()
        .replace(":", "_")
        .replace("[", "")
        .replace("]", "")
        .replace(" ", "_")
    )
    t = t.replace("-", "_")
    for i in tagpoints.ILLEGAL_NAME_CHARS:
        t = t.replace(i, "")

    return t


def onMidiMessageTuple(m, d):
    sb = m[0][0]
    code = sb & 240
    ch = sb & 15
    a = m[0][1]
    b = m[0][2]

    if code == 144:
        messagebus.post_message(f"/midi/{d}", ("noteon", ch, a, b))
        setTag(f"/midi/{d}/{str(ch)}.note", a, a=b)

    elif code == 128:
        messagebus.post_message(f"/midi/{d}", ("noteoff", ch, a, b))
        setTag(f"/midi/{d}/{str(ch)}.note", 0, a=0)

    elif code == 224:
        messagebus.post_message(f"/midi/{d}", ("pitch", ch, a, b))
        setTag14(f"/midi/{d}/{str(ch)}.pitch", a + b * 128, a=0)

    elif code == 176:
        messagebus.post_message(f"/midi/{d}", ("cc", ch, a, b))
        setTag(f"/midi/{d}/{str(ch)}.cc.{str(a)}", b, a=0)


once = [0]

scanning_connection = None

ctr = 0


def doScan():
    global scanning_connection, ctr

    try:
        import rtmidi
    except ImportError:
        if once[0] == 0:
            messagebus.post_message(
                "/system/notifications/errors/",
                "python-rtmidi is missing. Most MIDI related features will not work.",
            )
            once[0] = 1
        return

    if not scanning_connection:
        # Support versions of rtmidi where it does not work the first time
        scanning_connection = rtmidi.MidiIn(name=f"Kaithem{str(ctr)}")
        ctr += 1
    to_rm = []
    try:
        present = [
            (i, scanning_connection.get_port_name(i))
            for i in range(scanning_connection.get_port_count())
        ]
        scanning_connection.close_port()
    except Exception:
        scanning_connection = None
        raise

    for i in allInputs:
        if i not in present:
            to_rm.append(i)
    for i in to_rm:
        del allInputs[i]

    for i in present:
        if i not in allInputs:
            try:
                m = rtmidi.MidiIn()
                m.open_port(i[0])

                def f(
                    x,
                    *a,
                    d=normalize_midi_name(i[1]),
                ):
                    if isinstance(x, tuple):
                        try:
                            onMidiMessageTuple(x, d)
                        except Exception:
                            print(traceback.format_exc())
                    else:
                        try:
                            onMidiMessage(x, d)
                        except Exception:
                            print(traceback.format_exc())

                m.set_callback(f)
                allInputs[i] = (m, f)
            except Exception:
                print(f"Can't use MIDI:{str(i)}")


s = None


def init():
    global s
    s = scheduling.RepeatingEvent(doScan, 10)
    s.register()


init()
