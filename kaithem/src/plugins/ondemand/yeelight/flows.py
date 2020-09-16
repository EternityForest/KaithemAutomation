"""Built-in flows which the vendor ships in their app and pre-made transitions, for your strobing pleasure."""
from .flow import Action
from .flow import Flow
from .flow import RGBTransition
from .flow import TemperatureTransition
from yeelight import transitions


def disco(bpm=120):
    """
    Color changes to the beat.

    :param int bpm: The beats per minute to pulse to.

    :returns: An infinite Flow consisting of 8 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.disco(bpm))


def temp():
    """
    Slowly-changing color temperature.

    :returns: An infinite Flow consisting of 2 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.temp())


def strobe():
    """
    Rapid flashing on and off.

    :returns: An infinite Flow consisting of 2 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.strobe())


def pulse(red, green, blue, duration=250, brightness=100):
    """
    Pulse a single color once (mainly to be used for notifications).

    :param int red: The red color component to pulse (0-255).
    :param int green: The green color component to pulse (0-255).
    :param int blue: The blue color component to pulse (0-255).
    :param int duration: The duration to pulse for, in milliseconds.
    :param int brightness: The brightness to pulse at (1-100).

    :returns: A Flow consisting of 2 transitions, after which the bulb returns to its previous state.
    :rtype: Flow
    """
    return Flow(count=1, action=Action.recover, transitions=transitions.pulse(red, green, blue, duration, brightness))


def strobe_color(brightness=100):
    """
    Rapid flashing colors.

    :param int brightness: The brightness of the transition.

    :returns: An infinite Flow consisting of 6 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.strobe_color(brightness))


def alarm(duration=250):
    """
    Red alarm; flashing bright red to dark red.

    :param int duration: The duration between hi/lo brightness,in milliseconds.

    :returns: An infinite Flow consisting of 2 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.alarm(duration))


def police(duration=300, brightness=100):
    """
    Color changes from red to blue, like police lights.

    :param int duration: The duration between red and blue, in milliseconds.
    :param int brightness: The brightness of the transition.

    :returns: An infinite Flow consisting of 2 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.police(duration, brightness))


def police2(duration=250, brightness=100):
    """
    Color flashes red and then blue, like urgent police lights.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.

    :returns: An infinite Flow consisting of 8 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.police2(duration, brightness))


def lsd(duration=3000, brightness=100):
    """
    Gradual changes to a pleasing, trippy palette.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.

    :returns: An infinite Flow consisting of 5 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.lsd(duration, brightness))


def christmas(duration=250, brightness=100, sleep=3000):
    """
    Color changes from red to green, like christmas lights.

    :param int duration: The duration between red and green, in milliseconds.
    :param int brightness: The brightness of the transition.
    :param int sleep: The time to sleep between colors, in milliseconds.

    :returns: An infinite Flow consisting of 4 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.christmas(duration, brightness, sleep))


def rgb(duration=250, brightness=100, sleep=3000):
    """
    Color changes from red to green to blue.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.
    :param int sleep: The time to sleep between colors, in milliseconds

    :returns: An infinite Flow consisting of 6 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.rgb(duration, brightness, sleep))


def random_loop(duration=750, brightness=100, count=9):
    """
    Color changes between `count` randomly chosen colors.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.
    :param int count: The number of random chosen colors in transition.

    :returns: An infinite Flow consisting of up to 9 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.random_loop(duration, brightness, count))


def slowdown(duration=2000, brightness=100, count=8):
    """
    Changes between `count` random chosen colors with increasing transition time.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.
    :param int count: The number of random chosen colors in transition.

    :returns: An infinite Flow consisting of up to 8 transitions.
    :rtype: Flow
    """
    return Flow(count=0, action=Action.recover, transitions=transitions.slowdown(duration, brightness, count))


def home(duration=500, brightness=80):
    """
    Simulate daylight.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.

    :returns: An infinite Flow consisting of 1 transition.
    :rtype: Flow
    """
    transition = [TemperatureTransition(degrees=3200, duration=duration, brightness=brightness)]
    return Flow(count=0, action=Action.recover, transitions=transition)


def night_mode(duration=500, brightness=1):
    """
    Dim the lights to a dark red, pleasant for the eyes at night.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.

    :returns: An infinite Flow consisting of 1 transition.
    :rtype: Flow
    """
    transition = [RGBTransition(0xFF, 0x99, 0x00, duration=duration, brightness=brightness)]
    return Flow(count=0, action=Action.recover, transitions=transition)


def date_night(duration=500, brightness=50):
    """
    Dim the lights to a cozy orange.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.

    :returns: An infinite Flow consisting of 1 transition.
    :rtype: Flow
    """
    transition = [RGBTransition(0xFF, 0x66, 0x00, duration=duration, brightness=brightness)]
    return Flow(count=0, action=Action.recover, transitions=transition)


def movie(duration=500, brightness=50):
    """
    Dim the lights to a comfy purple.

    :param int duration: The duration to fade to next color, in milliseconds.
    :param int brightness: The brightness of the transition.

    :returns: An infinite Flow consisting of 1 transition.
    :rtype: Flow
    """
    transition = [RGBTransition(red=0x14, green=0x14, blue=0x32, duration=duration, brightness=brightness)]
    return Flow(count=0, action=Action.recover, transitions=transition)


def sunrise():
    """
    Simulate a natural and gentle sunrise in 15 minutes.

    :returns: A Flow consisting of 3 transitions, after which the bulb stays on.
    :rtype: Flow
    """
    transitions = [
        RGBTransition(red=0xFF, green=0x4D, blue=0x00, duration=50, brightness=1),
        TemperatureTransition(degrees=1700, duration=360000, brightness=10),
        TemperatureTransition(degrees=2700, duration=540000, brightness=100),
    ]
    return Flow(count=1, action=Action.stay, transitions=transitions)


def sunset():
    """
    Simulate a natural sunset and offering relaxing dimming to help you sleep in 10 minutes.

    :returns: A Flow consisting of 3 transitions, after which the bulb turns off.
    :rtype: Flow
    """
    transitions = [
        TemperatureTransition(degrees=2700, duration=50, brightness=10),
        TemperatureTransition(degrees=1700, duration=180000, brightness=5),
        RGBTransition(red=0xFF, green=0x4C, blue=0x00, duration=420000, brightness=1),
    ]
    return Flow(count=1, action=Action.off, transitions=transitions)


def romance():
    """
    Romantic lights.

    :returns: An infinite Flow consisting of 2 transitions.
    :rtype: Flow
    """
    transitions = [
        RGBTransition(red=0x59, green=0x15, blue=0x6D, duration=4000, brightness=1),
        RGBTransition(red=0x66, green=0x14, blue=0x2A, duration=4000, brightness=1),
    ]
    return Flow(count=0, action=Action.stay, transitions=transitions)


def happy_birthday():
    """
    Happy Birthday lights.

    :returns: An infinite Flow consisting of 3 transitions.
    :rtype: Flow
    """
    transitions = [
        RGBTransition(red=0xDC, green=0x50, blue=0x19, duration=1996, brightness=80),
        RGBTransition(red=0xDC, green=0x78, blue=0x1E, duration=1996, brightness=80),
        RGBTransition(red=0xAA, green=0x32, blue=0x14, duration=1996, brightness=80),
    ]
    return Flow(count=0, action=Action.stay, transitions=transitions)


def candle_flicker():
    """
    Simulate candle flicker.

    :returns: An infinite Flow consisting of 9 transitions.
    :rtype: Flow
    """
    transitions = [
        TemperatureTransition(degrees=2700, duration=800, brightness=50),
        TemperatureTransition(degrees=2700, duration=800, brightness=30),
        TemperatureTransition(degrees=2700, duration=1200, brightness=80),
        TemperatureTransition(degrees=2700, duration=800, brightness=60),
        TemperatureTransition(degrees=2700, duration=1200, brightness=90),
        TemperatureTransition(degrees=2700, duration=2400, brightness=50),
        TemperatureTransition(degrees=2700, duration=1200, brightness=80),
        TemperatureTransition(degrees=2700, duration=800, brightness=60),
        TemperatureTransition(degrees=2700, duration=400, brightness=70),
    ]
    return Flow(count=0, action=Action.recover, transitions=transitions)
