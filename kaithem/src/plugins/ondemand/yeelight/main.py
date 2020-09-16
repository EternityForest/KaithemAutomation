# encoding: utf8
import colorsys
import json
import logging
import socket

from future.utils import raise_from

from .decorator import decorator  # type: ignore
from .enums import BulbType
from .enums import LightType
from .enums import PowerMode
from .enums import SceneClass
from .flow import Flow
from .ssdp_discover import filter_lower_case_keys
from .ssdp_discover import parse_capabilities
from .ssdp_discover import send_discovery_packet
from .utils import _clamp
from .utils import rgb_to_yeelight


try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse  # type: ignore

_LOGGER = logging.getLogger(__name__)

_MODEL_SPECS = {
    "bslamp1": {"color_temp": {"min": 1700, "max": 6500}, "night_light": False, "background_light": False},
    "bslamp2": {"color_temp": {"min": 1700, "max": 6500}, "night_light": True, "background_light": False},
    "ceiling13": {"color_temp": {"min": 2700, "max": 6500}, "night_light": True, "background_light": False},
    "ceiling1": {"color_temp": {"min": 2700, "max": 6500}, "night_light": True, "background_light": False},
    "ceiling2": {"color_temp": {"min": 2700, "max": 6500}, "night_light": True, "background_light": False},
    "ceiling3": {"color_temp": {"min": 2700, "max": 6500}, "night_light": True, "background_light": False},
    "ceiling4": {"color_temp": {"min": 2700, "max": 6500}, "night_light": True, "background_light": True},
    "ceiling5": {"color_temp": {"min": 2700, "max": 5700}, "night_light": True, "background_light": False},
    "color1": {"color_temp": {"min": 1700, "max": 6500}, "night_light": False, "background_light": False},
    "color2": {"color_temp": {"min": 2700, "max": 6500}, "night_light": False, "background_light": False},
    "color": {"color_temp": {"min": 1700, "max": 6500}, "night_light": False, "background_light": False},
    "ct_bulb": {"color_temp": {"min": 2700, "max": 6500}, "night_light": False, "background_light": False},
    "mono1": {"color_temp": {"min": 2700, "max": 2700}, "night_light": False, "background_light": False},
    "mono": {"color_temp": {"min": 2700, "max": 2700}, "night_light": False, "background_light": False},
    "strip1": {"color_temp": {"min": 1700, "max": 6500}, "night_light": False, "background_light": False},
}


def get_known_models():
    """
    Helper method to return all known yeelight models.

    The models spec dict is private and internal, this function allows consumers to get
    a list of models via a public method.
    """
    return list(_MODEL_SPECS.keys())


@decorator
def _command(f, *args, **kw):
    """A decorator that wraps a function and enables effects."""
    self = args[0]
    effect = kw.get("effect", self.effect)
    duration = kw.get("duration", self.duration)
    power_mode = kw.get("power_mode", self.power_mode)

    method, params, kwargs = f(*args, **kw)

    light_type = kwargs.get("light_type", LightType.Main)

    # Prepend the control for different bulbs
    if light_type == LightType.Ambient:
        method = "bg_" + method

    if method in [
        "set_ct_abx",
        "set_rgb",
        "set_hsv",
        "set_bright",
        "set_power",
        "toggle",
        "bg_set_ct_abx",
        "bg_set_rgb",
        "bg_set_hsv",
        "bg_set_bright",
        "bg_set_power",
        "bg_toggle",
    ]:
        if self._music_mode:
            # Mapping calls to their properties.
            # Used to keep music mode cache up to date.
            action_property_map = {
                "set_ct_abx": ["ct"],
                "bg_set_ct_abx": ["bg_ct"],
                "set_rgb": ["rgb"],
                "bg_set_rgb": ["bg_rgb"],
                "set_hsv": ["hue", "sat"],
                "bg_set_hsv": ["bg_hue", "bg_sat"],
                "set_bright": ["bright"],
                "bg_set_bright": ["bg_bright"],
                "set_power": ["power"],
                "bg_set_power": ["bg_power"],
            }
            # Handle toggling separately, as it depends on a previous power state.
            if method == "toggle":
                self._last_properties["power"] = "on" if self._last_properties["power"] == "off" else "off"
            if method == "bg_toggle":
                self._last_properties["bg_power"] = "on" if self._last_properties["bg_power"] == "off" else "off"
            # dev_toggle toggle both lights depending on the MAIN light power status.
            if method == "dev_toggle":
                new_state = "on" if self._last_properties["power"] == "off" else "off"
                self._last_properties["power"] = new_state
                self._last_properties["bg_power"] = new_state
            elif method in action_property_map:
                set_prop = action_property_map[method]
                update_props = {set_prop[prop]: params[prop] for prop in range(len(set_prop))}
                _LOGGER.debug("Music mode cache update: %s", update_props)
                self._last_properties.update(update_props)
        # Add the effect parameters.
        params += [effect, duration]
        # Add power_mode parameter.
        if method == "set_power" and params[0] == "on" and power_mode.value != PowerMode.LAST:
            params += [power_mode.value]
        if method == "bg_set_power" and params[0] == "on" and power_mode.value != PowerMode.LAST:
            params += [power_mode.value]

    result = self.send_command(method, params).get("result", [])
    if result:
        return result[0]


def discover_bulbs(timeout=2, interface=False):
    """
    Discover all the bulbs in the local network.

    :param int timeout: How many seconds to wait for replies. Discovery will
                        always take exactly this long to run, as it can't know
                        when all the bulbs have finished responding.

    :param string interface: The interface that should be used for multicast packets.
                             Note: it *has* to have a valid IPv4 address. IPv6-only
                             interfaces are not supported (at the moment).
                             The default one will be used if this is not specified.

    :returns: A list of dictionaries, containing the ip, port and capabilities
              of each of the bulbs in the network.
    """
    s = send_discovery_packet(timeout, interface)

    bulbs = []
    bulb_ips = set()
    while True:
        try:
            data, addr = s.recvfrom(65507)
        except socket.timeout:
            break

        capabilities = parse_capabilities(data)
        parsed_url = urlparse(capabilities["Location"])

        bulb_ip = (parsed_url.hostname, parsed_url.port)
        if bulb_ip in bulb_ips:
            continue

        capabilities = filter_lower_case_keys(capabilities)
        bulbs.append({"ip": bulb_ip[0], "port": bulb_ip[1], "capabilities": capabilities})
        bulb_ips.add(bulb_ip)

    return bulbs


class BulbException(Exception):
    """
    A generic yeelight exception.

    This exception is raised when bulb informs about errors, e.g., when trying
    to issue unsupported commands to the bulb.
    """

    pass


class Bulb(object):
    def __init__(
        self, ip, port=55443, effect="smooth", duration=300, auto_on=False, power_mode=PowerMode.LAST, model=None
    ):
        """
        The main controller class of a physical YeeLight bulb.

        :param str ip:       The IP of the bulb.
        :param int port:     The port to connect to on the bulb.
        :param str effect:   The type of effect. Can be "smooth" or "sudden".
        :param int duration: The duration of the effect, in milliseconds. The
                             minimum is 30. This is ignored for sudden effects.
        :param bool auto_on: Whether to call :py:meth:`ensure_on()
                             <yeelight.Bulb.ensure_on>` to turn the bulb on
                             automatically before each operation, if it is off.
                             This renews the properties of the bulb before each
                             message, costing you one extra message per command.
                             Turn this off and do your own checking with
                             :py:meth:`get_properties()
                             <yeelight.Bulb.get_properties()>` or run
                             :py:meth:`ensure_on() <yeelight.Bulb.ensure_on>`
                             yourself if you're worried about rate-limiting.
        :param yeelight.PowerMode power_mode:
                             The mode for the light set when powering on.
        :param str model:    The model name of the yeelight (e.g. "color",
                             "mono", etc). The setting is used to enable model
                             specific features (e.g. a particular color
                             temperature range).

        """
        self._ip = ip
        self._port = port

        self.effect = effect
        self.duration = duration
        self.auto_on = auto_on
        self.power_mode = power_mode
        self._model = model

        self.__cmd_id = 0  # The last command id we used.
        self._last_properties = {}  # The last set of properties we've seen.
        self._capabilities = {}  # Capabilites obtained via SSDP Discovery.
        self._music_mode = False  # Whether we're currently in music mode.
        self.__socket = None  # The socket we use to communicate.

        self._notification_socket = None  # The socket to get update notifications
        self._is_listening = False  # Indicate if we are listening

    @property
    def _cmd_id(self):
        """
        Return the next command ID and increment the counter.

        :rtype: int
        """
        self.__cmd_id += 1
        return self.__cmd_id - 1

    @property
    def _socket(self):
        """Return, optionally creating, the communication socket."""
        if self.__socket is None:
            self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__socket.settimeout(5)
            self.__socket.connect((self._ip, self._port))
        return self.__socket

    def get_capabilities(self, timeout=2):
        """
        Get the bulb's capabilities using the discovery protocol.

        :param int timeout: How many seconds to wait for replies. Discovery will
                            always take exactly this long to run, as it can't know
                            when all the bulbs have finished responding.

        :returns: Dictionary, containing the ip, port and capabilities. For example:
                  {
                  'id': '0x0000000002eb9f61',
                  'model': 'ceiling3',
                  'fw_ver': '43',
                  'support': 'get_prop set_default set_power toggle set_bright set_scene cron_add cron_get cron_del start_cf stop_cf set_ct_abx set_name set_adjust adjust_bright adjust_ct',
                  'power': 'on',
                  'bright': '99',
                  'color_mode': '2',
                  'ct': '3802',
                  'rgb': '0',
                  'hue': '0',
                  'sat': '0',
                  'name': ''
                  }
        """
        s = send_discovery_packet(timeout, ip_address=self._ip)

        try:
            data, addr = s.recvfrom(65507)
        except socket.timeout:
            return None

        capabilities = parse_capabilities(data)
        capabilities = filter_lower_case_keys(capabilities)

        self._capabilities = capabilities
        return capabilities

    def ensure_on(self):
        """Turn the bulb on if it is off."""
        if self._music_mode is True or self.auto_on is False:
            return

        self.get_properties()

        if self._last_properties["power"] != "on":
            self.turn_on()

    @property
    def last_properties(self):
        """
        The last properties we've seen the bulb have.

        This might potentially be out of date, as there's no background listener
        for the bulb's notifications. To update it, call
        :py:meth:`get_properties <yeelight.Bulb.get_properties()>`.
        """
        return self._last_properties

    @property
    def capabilities(self):
        """
        Capabilities obtained via SSDP Discovery.

        They will be empty, unless updated via:
        :py:meth:`get_capabilities <yeelight.Bulb.get_capabilities()>`.

        :return: Capabilities dict returned by :py:meth:`get_capabilities`.
        """
        return self._capabilities

    @property
    def bulb_type(self):
        """
        The type of bulb we're communicating with.

        Returns a :py:class:`BulbType <yeelight.BulbType>` describing the bulb
        type.

        When trying to access before properties are known, the bulb type is unknown.

        :rtype: yeelight.BulbType
        :return: The bulb's type.
        """
        if not self._last_properties or any(name not in self.last_properties for name in ["ct", "rgb"]):
            return BulbType.Unknown
        if self.last_properties["rgb"] is None and self.last_properties["ct"]:
            if self.last_properties["bg_power"] is not None:
                return BulbType.WhiteTempMood
            else:
                return BulbType.WhiteTemp
        if all(
            name in self.last_properties and self.last_properties[name] is None for name in ["ct", "rgb", "hue", "sat"]
        ):
            return BulbType.White
        else:
            return BulbType.Color

    @property
    def model(self):
        """
        Return declared model / model discovered via SSDP Discovery or None.

        :return: Device model
        """
        if self._model:
            return self._model
        elif "model" in self.capabilities:
            return self.capabilities["model"]
        else:
            return None

    @property
    def music_mode(self):
        """
        Return whether the music mode is active.

        :rtype: bool
        :return: True if music mode is on, False otherwise.
        """
        return self._music_mode

    def listen(self, callback):
        """
        Listen to state update notifications.

        This function is blocking until a socket error occurred or being stopped by
        ``stop_listening``. It should be run in a ``Thread`` or ``asyncio`` event loop.

        The callback function should take one parameter, containing the new/updates
        properties. It will be called when ``last_properties`` is updated.

        :param callable callback: A callback function to receive state update notification.
        """
        try:
            self._is_listening = True
            self._notification_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._notification_socket.setblocking(True)
            self._notification_socket.connect((self._ip, self._port))
            while self._notification_socket is not None:
                data = self._notification_socket.recv(16 * 1024)
                for line in data.split(b"\r\n"):
                    if not line:
                        continue
                    try:
                        line = json.loads(line.decode("utf8"))
                    except ValueError:
                        _LOGGER.error("Invalid data: %s", line)
                        continue

                    if line.get("method") == "props":
                        # Update notification received
                        _LOGGER.debug("New props received: %s", line)
                        self._last_properties.update(line["params"])
                        callback(line["params"])
        except socket.error as ex:
            if not self._is_listening:
                # Socket is manually shutdown by stop_listening
                return
            self._notification_socket.close()
            self._notification_socket = None
            raise_from(BulbException("Failed to read from the socket."), ex)

    def stop_listening(self):
        """Stop listening to notifications."""
        self._is_listening = False
        self._notification_socket.shutdown(socket.SHUT_RDWR)
        self._notification_socket.close()
        self._notification_socket = None

    def get_properties(
        self,
        requested_properties=[
            "power",
            "bright",
            "ct",
            "rgb",
            "hue",
            "sat",
            "color_mode",
            "flowing",
            "delayoff",
            "music_on",
            "name",
            "bg_power",
            "bg_flowing",
            "bg_ct",
            "bg_bright",
            "bg_hue",
            "bg_sat",
            "bg_rgb",
            "nl_br",
            "active_mode",
        ],
    ):
        """
        Retrieve and return the properties of the bulb.

        This method also updates ``last_properties`` when it is called.

        The ``current_brightness`` property is calculated by the library (i.e. not returned
        by the bulb), and indicates the current brightness of the lamp, aware of night light
        mode. It is 0 if the lamp is off, and None if it is unknown.

        :param list requested_properties: The list of properties to request from the bulb.
                                          By default, this does not include ``flow_params``.

        :returns: A dictionary of param: value items.
        :rtype: dict
        """
        # When we are in music mode, the bulb does not respond to queries
        # therefore we need to keep the state up-to-date ourselves
        if self._music_mode:
            return self._last_properties

        response = self.send_command("get_prop", requested_properties)
        properties = response["result"]
        properties = [x if x else None for x in properties]

        self._last_properties = dict(zip(requested_properties, properties))

        if self._last_properties.get("power") == "off":
            cb = "0"
        if self._last_properties.get("bg_power") == "off":
            cb = "0"
        elif self._last_properties.get("active_mode") == "1":
            # Nightlight mode.
            cb = self._last_properties.get("nl_br")
        else:
            cb = self._last_properties.get("bright")
        self._last_properties["current_brightness"] = cb

        return self._last_properties

    def send_command(self, method, params=None):
        """
        Send a command to the bulb.

        :param str method:  The name of the method to send.
        :param list params: The list of parameters for the method.

        :raises BulbException: When the bulb indicates an error condition.
        :returns: The response from the bulb.
        """
        command = {"id": self._cmd_id, "method": method, "params": params}

        _LOGGER.debug("%s > %s", self, command)

        try:
            self._socket.send((json.dumps(command) + "\r\n").encode("utf8"))
        except socket.error as ex:
            # Some error occurred, remove this socket in hopes that we can later
            # create a new one.
            self.__socket.close()
            self.__socket = None
            raise_from(BulbException("A socket error occurred when sending the command."), ex)

        if self._music_mode:
            # We're in music mode, nothing else will happen.
            return {"result": ["ok"]}

        # The bulb will send us updates on its state in addition to responses,
        # so we want to make sure that we read until we see an actual response.
        response = None
        while response is None:
            try:
                data = self._socket.recv(16 * 1024)
            except socket.error:
                # An error occured, let's close and abort...
                self.__socket.close()
                self.__socket = None
                response = {"error": "Bulb closed the connection."}
                break

            for line in data.split(b"\r\n"):
                if not line:
                    continue

                try:
                    line = json.loads(line.decode("utf8"))
                    _LOGGER.debug("%s < %s", self, line)
                except ValueError:
                    line = {"result": ["invalid command"]}

                if line.get("method") != "props":
                    # This is probably the response we want.
                    response = line
                else:
                    self._last_properties.update(line["params"])

        if method == "set_music" and params == [0] and "error" in response and response["error"]["code"] == -5000:
            # The bulb seems to throw an error for no reason when stopping music mode,
            # it doesn't affect operation and we can't do anything about it, so we might
            # as well swallow it.
            return {"id": 1, "result": ["ok"]}

        if "error" in response:
            raise BulbException(response["error"])

        return response

    @_command
    def set_color_temp(self, degrees, light_type=LightType.Main, **kwargs):
        """
        Set the bulb's color temperature.

        :param int degrees: The degrees to set the color temperature to (min/max are
                            specified by the model's capabilities, or 1700-6500).
        :param yeelight.LightType light_type: Light type to control.
        """
        self.ensure_on()

        return ("set_ct_abx", [self._clamp_color_temp(degrees)], dict(kwargs, light_type=light_type))

    @_command
    def set_rgb(self, red, green, blue, light_type=LightType.Main, **kwargs):
        """
        Set the bulb's RGB value.

        :param int red:   The red value to set (0-255).
        :param int green: The green value to set (0-255).
        :param int blue:  The blue value to set (0-255).
        :param yeelight.LightType light_type:
                          Light type to control.
        """
        self.ensure_on()

        return ("set_rgb", [rgb_to_yeelight(red, green, blue)], dict(kwargs, light_type=light_type))

    @_command
    def set_adjust(self, action, prop, **kwargs):
        """
        Adjust a parameter.

        I don't know what this is good for. I don't know how to use it, or why.
        I'm just including it here for completeness, and because it was easy,
        but it won't get any particular love.

        :param str action: The direction of adjustment. Can be "increase",
                           "decrease" or "circle".
        :param str prop:   The property to adjust. Can be "bright" for
                           brightness, "ct" for color temperature and "color"
                           for color. The only action for "color" can be
                           "circle". Why? Who knows.
        """
        return "set_adjust", [action, prop], kwargs

    @_command
    def set_hsv(self, hue, saturation, value=None, light_type=LightType.Main, **kwargs):
        """
        Set the bulb's HSV value.

        :param int hue:        The hue to set (0-359).
        :param int saturation: The saturation to set (0-100).
        :param int value:      The value to set (0-100). If omitted, the bulb's
                               brightness will remain the same as before the
                               change.
        :param yeelight.LightType light_type: Light type to control.
        """
        self.ensure_on()

        # We fake this using flow so we can add the `value` parameter.
        hue = _clamp(hue, 0, 359)
        saturation = _clamp(saturation, 0, 100)

        if value is None:
            # If no value was passed, use ``set_hsv`` to preserve luminance.
            return "set_hsv", [hue, saturation], dict(kwargs, light_type=light_type)
        else:
            # Otherwise, use flow.
            value = _clamp(value, 0, 100)

            if kwargs.get("effect", self.effect) == "sudden":
                duration = 50
            else:
                duration = kwargs.get("duration", self.duration)

            hue = _clamp(hue, 0, 359) / 359.0
            saturation = _clamp(saturation, 0, 100) / 100.0
            rgb = rgb_to_yeelight(*[int(round(col * 255)) for col in colorsys.hsv_to_rgb(hue, saturation, 1)])
            return ("start_cf", [1, 1, "%s, 1, %s, %s" % (duration, rgb, value)], dict(kwargs, light_type=light_type))

    @_command
    def set_brightness(self, brightness, light_type=LightType.Main, **kwargs):
        """
        Set the bulb's brightness.

        :param int brightness: The brightness value to set (1-100).
        :param yeelight.LightType light_type: Light type to control.
        """
        self.ensure_on()

        brightness = _clamp(brightness, 1, 100)
        return "set_bright", [brightness], dict(kwargs, light_type=light_type)

    @_command
    def turn_on(self, light_type=LightType.Main, **kwargs):
        """
        Turn the bulb on.

        :param yeelight.LightType light_type: Light type to control.
        """
        return "set_power", ["on"], dict(kwargs, light_type=light_type)

    @_command
    def turn_off(self, light_type=LightType.Main, **kwargs):
        """
        Turn the bulb off.

        :param yeelight.LightType light_type: Light type to control.
        """
        return "set_power", ["off"], dict(kwargs, light_type=light_type)

    @_command
    def toggle(self, light_type=LightType.Main, **kwargs):
        """
        Toggle the bulb on or off.

        :param yeelight.LightType light_type: Light type to control.
        """
        return "toggle", [], dict(kwargs, light_type=light_type)

    @_command
    def dev_toggle(self, **kwargs):
        """Toggle the main light and the ambient on or off."""
        return "dev_toggle", [], kwargs

    @_command
    def set_default(self, light_type=LightType.Main, **kwargs):
        """
        Set the bulb's current state as the default, which is what the bulb will be set to on power on.

        If you get a "general error" setting this, yet the bulb reports as supporting `set_default` during
        discovery, disable "auto save settings" in the YeeLight app.

        :param yeelight.LightType light_type: Light type to control.
        """
        return "set_default", [], dict(kwargs, light_type=light_type)

    @_command
    def set_name(self, name, **kwargs):
        """
        Set the bulb's name.

        :param str name: The string you want to set as the bulb's name.
        """
        return "set_name", [name], kwargs

    @_command
    def start_flow(self, flow, light_type=LightType.Main, **kwargs):
        """
        Start a flow.

        :param yeelight.Flow flow: The Flow instance to start.
        """
        if not isinstance(flow, Flow):
            raise ValueError("Argument is not a Flow instance.")

        self.ensure_on()

        return ("start_cf", flow.as_start_flow_params, dict(kwargs, light_type=light_type))

    @_command
    def stop_flow(self, light_type=LightType.Main, **kwargs):
        """
        Stop a flow.

        :param yeelight.LightType light_type: Light type to control.
        """
        return "stop_cf", [], dict(kwargs, light_type=light_type)

    @_command
    def set_scene(self, scene_class, *args, **kwargs):
        """
        Set the light directly to the specified state.

        If the light is off, it will first be turned on.

        :param yeelight.SceneClass scene_class: The YeeLight scene class to use.

        * `COLOR` changes the light to the specified RGB color and brightness.

            Arguments:
            * **red** (*int*)         – The red value to set (0-255).
            * **green** (*int*)       – The green value to set (0-255).
            * **blue** (*int*)        – The blue value to set (0-255).
            * **brightness** (*int*)  – The brightness value to set (1-100).

        * `HSV` changes the light to the specified HSV color and brightness.

            Arguments:
            * **hue** (*int*)         – The hue to set (0-359).
            * **saturation** (*int*)  – The saturation to set (0-100).
            * **brightness** (*int*)  – The brightness value to set (1-100).

        * `CT` changes the light to the specified color temperature.

            Arguments:
            * **degrees** (*int*)     – The degrees to set the color temperature to (min/max are specified by the
            model's capabilities, or 1700-6500).
            * **brightness** (*int*)  – The brightness value to set (1-100).

        * `CF` starts a color flow.

            Arguments:
            * **flow** (`yeelight.Flow`)  – The Flow instance to start.

        * `AUTO_DELAY_OFF` turns the light on to the specified brightness and sets a timer to turn it back off after the
          given number of minutes.

            Arguments:
            * **brightness** (*int*)     – The brightness value to set (1-100).
            * **minutes** (*int*)        – The minutes to wait before automatically turning the light off.

        :param yeelight.LightType light_type: Light type to control.
        """
        scene_args = [scene_class.name.lower()]
        if scene_class == SceneClass.COLOR:
            scene_args += [rgb_to_yeelight(*args[:3]), args[3]]
        elif scene_class == SceneClass.HSV:
            scene_args += args
        elif scene_class == SceneClass.CT:
            scene_args += [self._clamp_color_temp(args[0]), args[1]]
        elif scene_class == SceneClass.CF:
            scene_args += args[0].as_start_flow_params
        elif scene_class == SceneClass.AUTO_DELAY_OFF:
            scene_args += args
        else:
            raise ValueError("Scene class argument is unknown. Please use one from yeelight.SceneClass.")

        return "set_scene", scene_args, kwargs

    def start_music(self, port=0, ip=None):
        """
        Start music mode.

        Music mode essentially upgrades the existing connection to a reverse one
        (the bulb connects to the library), removing all limits and allowing you
        to send commands without being rate-limited.

        Starting music mode will start a new listening socket, tell the bulb to
        connect to that, and then close the old connection. If the bulb cannot
        connect to the host machine for any reason, bad things will happen (such
        as library freezes).

        :param int port: The port to listen on. If none is specified, a random
                         port will be chosen.

        :param str ip: The IP address of the host this library is running on.
                       Will be discovered automatically if not provided.
        """
        if self._music_mode:
            raise AssertionError("Already in music mode, please stop music mode first.")

        # Force populating the cache in case we are being called directly
        # without ever fetching properties beforehand
        self.get_properties()

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Reuse sockets so we don't hit "address already in use" errors.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", port))
        host, port = s.getsockname()
        s.listen(3)

        local_ip = ip if ip else self._socket.getsockname()[0]
        self.send_command("set_music", [1, local_ip, port])
        s.settimeout(5)
        conn, _ = s.accept()
        s.close()  # Close the listening socket.
        self.__socket.close()
        self.__socket = conn
        self._music_mode = True

        return "ok"

    @_command
    def stop_music(self, **kwargs):
        """
        Stop music mode.

        Stopping music mode will close the previous connection. Calling
        ``stop_music`` more than once, or while not in music mode, is safe.
        """
        if self.__socket:
            self.__socket.close()
            self.__socket = None
        self._music_mode = False
        return "set_music", [0], kwargs

    @_command
    def cron_add(self, event_type, value, **kwargs):
        """
        Add an event to cron.

        Example::

        >>> bulb.cron_add(CronType.off, 10)

        :param yeelight.CronType event_type: The type of event. Currently,
                                                   only ``CronType.off``.
        """
        return "cron_add", [event_type.value, value], kwargs

    @_command
    def cron_get(self, event_type, **kwargs):
        """
        Retrieve an event from cron.

        :param yeelight.CronType event_type: The type of event. Currently,
                                                   only ``CronType.off``.
        """
        return "cron_get", [event_type.value], kwargs

    @_command
    def cron_del(self, event_type, **kwargs):
        """
        Remove an event from cron.

        :param yeelight.CronType event_type: The type of event. Currently,
                                                   only ``CronType.off``.
        """
        return "cron_del", [event_type.value], kwargs

    def __repr__(self):
        return "Bulb<{ip}:{port}, type={type}>".format(ip=self._ip, port=self._port, type=self.bulb_type)

    def set_power_mode(self, mode):
        """
        Set the light power mode.

        If the light is off it will be turned on.

        :param yeelight.PowerMode mode: The mode to switch to.
        """
        return self.turn_on(power_mode=mode)

    def get_model_specs(self, **kwargs):
        """Return the specifications (e.g. color temperature min/max) of the bulb."""
        if self.model is not None and self.model in _MODEL_SPECS:
            return _MODEL_SPECS[self.model]

        _LOGGER.debug("Model unknown (%s). Providing a fallback", self.model)
        if self.bulb_type is BulbType.White:
            return _MODEL_SPECS["mono"]

        if self.bulb_type is BulbType.WhiteTemp:
            return _MODEL_SPECS["ceiling1"]

        if self.bulb_type is BulbType.WhiteTempMood:
            return _MODEL_SPECS["ceiling4"]

        # BulbType.Color and BulbType.Unknown
        return _MODEL_SPECS["color"]

    def _clamp_color_temp(self, degrees):
        """
        Clamp color temp to correct range.

        :param int degrees: The degrees to set the color temperature to specified by model or defaults
        (1700-6500).
        """
        if self.model:
            color_specs = self.get_model_specs()["color_temp"]
            return _clamp(degrees, color_specs["min"], color_specs["max"])

        return _clamp(degrees, 1700, 6500)
