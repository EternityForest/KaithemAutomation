def rgb_to_yeelight(red, green, blue):
    """
    Calculate the YeeLight-compatible single color value from individual RGB values.

    :param red:
    :param green:
    :param blue:
    """
    red = _clamp(red, 0, 255)
    green = _clamp(green, 0, 255)
    blue = _clamp(blue, 0, 255)

    return red * 65536 + green * 256 + blue


def _clamp(value, minx, maxx):
    """
    Constrain a value between a minimum and a maximum.

    If the value is larger than the maximum or lower than the minimum, the
    maximum or minimum will be returned instead.

    :param int value: The value to clamp.
    :param int minx: The minimum the value can take.
    :param int maxx: The maximum the value can take.
    """
    return max(minx, min(maxx, value))
