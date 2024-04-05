# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

from . import tagpoints
from scullery import messagebus
from . import scheduling
import traceback

allInputs = {}

tagPoints = {}


def setTag(n, v, a=None):
    if n not in tagPoints:
        tagPoints[n] = tagpoints.Tag(n)
        tagPoints[n].min = 0
        tagPoints[n].max = 127
    tagPoints[n].setClaimVal("default", v, timestamp=None, annotation=None)


def setTag14(n, v, a=None):
    if n not in tagPoints:
        tagPoints[n] = tagpoints.Tag(n)
        tagPoints[n].min = 0
        tagPoints[n].max = 16383
    tagPoints[n].setClaimVal("default", v, timestamp=None, annotation=None)


def onMidiMessage(m, d):
    if m.isNoteOn():
        messagebus.post_message(
            "/midi/" + d, ("noteon", m.getChannel(), m.getNoteNumber(), m.getVelocity())
        )
        setTag(
            "/midi/" + d + "/" + str(m.getChannel()) + ".note",
            m.getNoteNumber(),
            a=m.getVelocity(),
        )

    elif m.isNoteOff():
        messagebus.post_message(
            "/midi/" + d, ("noteoff", m.getChannel(), m.getNoteNumber())
        )
        setTag("/midi/" + d + "/" + str(m.getChannel()) + ".note", 0, a=0)

    elif m.isController():
        messagebus.post_message(
            "/midi/" + d,
            ("cc", m.getChannel(), m.getControllerNumber(), m.getControllerValue()),
        )
        setTag(
            "/midi/"
            + d
            + "/"
            + str(m.getChannel())
            + ".cc["
            + str(m.getControllerNumber())
            + "]",
            m.getControllerValue(),
            a=0,
        )

    elif m.isPitchWheel():
        messagebus.post_message(
            "/midi/" + d, ("pitch", m.getChannel(), m.getPitchWheelValue())
        )
        setTag14(
            "/midi/" + d + "/" + str(m.getChannel()) + ".pitch",
            m.getPitchWheelValue(),
            a=0,
        )


def normalizetag(t):
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
        messagebus.post_message("/midi/" + d, ("noteon", ch, a, b))
        setTag("/midi/" + normalizetag(d) + "/" + str(ch) + ".note", a, a=b)

    elif code == 128:
        messagebus.post_message("/midi/" + d, ("noteoff", ch, a, b))
        setTag("/midi/" + normalizetag(d) + "/" + str(ch) + ".note", 0, a=0)

    elif code == 224:
        messagebus.post_message("/midi/" + d, ("pitch", ch, a, b))
        setTag14(
            "/midi/" + normalizetag(d) + "/" + str(ch) + ".pitch", a + b * 128, a=0
        )

    elif code == 176:
        messagebus.post_message("/midi/" + d, ("cc", ch, a, b))
        setTag(
            "/midi/" + normalizetag(d) + "/" + str(ch) + ".cc[" + str(a) + "]", b, a=0
        )


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
        try:
            scanning_connection = rtmidi.MidiIn(
                rtmidi.API_UNIX_JACK, name="Kaithem" + str(ctr)
            )
        except Exception:
            scanning_connection = rtmidi.MidiIn(
                rtmidi.API_UNIX_JACK, name="Kaithem" + str(ctr)
            )
        ctr += 1
    torm = []
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
            torm.append(i)
    for i in torm:
        del allInputs[i]

    for i in present:
        if i not in allInputs:
            try:
                m = rtmidi.MidiIn(rtmidi.API_UNIX_JACK)
                m.open_port(i[0])

                def f(
                    x,
                    *a,
                    d=i[1]
                    .replace(":", "_")
                    .replace("[", "")
                    .replace("]", "")
                    .replace(" ", ""),
                ):
                    if isinstance(x, tuple):
                        try:
                            onMidiMessageTuple(x, d)
                        except:
                            print(traceback.format_exc())
                    else:
                        try:
                            onMidiMessage(x, d)
                        except:
                            print(traceback.format_exc())

                m.set_callback(f)
                allInputs[i] = (m, f)
            except Exception:
                print("Can't use MIDI:" + str(i))


s = None


def init():
    global s
    s = scheduling.UnsynchronizedRepeatingEvent(doScan, 10)
    s.schedule()
