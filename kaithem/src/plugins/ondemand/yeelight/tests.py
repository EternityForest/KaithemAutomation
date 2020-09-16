import json
import os
import sys
import threading
import time
import unittest

import mock

from yeelight import Bulb
from yeelight import enums
from yeelight import Flow
from yeelight import flows
from yeelight import TemperatureTransition
from yeelight.enums import LightType
from yeelight.enums import SceneClass
from yeelight.flow import Action

sys.path.insert(0, os.path.abspath(__file__ + "/../.."))


class SocketMock(object):
    def __init__(self, received=b'{"id": 0, "result": ["ok"]}'):
        self.received = received

    def send(self, data):
        self.sent = json.loads(data.decode("utf8"))

    def recv(self, length):
        return self.received


class Tests(unittest.TestCase):
    def setUp(self):
        self.socket = SocketMock()
        self.bulb = Bulb(ip="", auto_on=True)
        self.bulb._Bulb__socket = self.socket

    def test_rgb1(self):
        self.bulb.set_rgb(255, 255, 0)
        self.assertEqual(self.socket.sent["method"], "set_rgb")
        self.assertEqual(self.socket.sent["params"], [16776960, "smooth", 300])

    def test_rgb2(self):
        self.bulb.effect = "sudden"
        self.bulb.set_rgb(255, 255, 0)
        self.assertEqual(self.socket.sent["method"], "set_rgb")
        self.assertEqual(self.socket.sent["params"], [16776960, "sudden", 300])

    def test_rgb3(self):
        self.bulb.set_rgb(255, 255, 0, effect="sudden")
        self.assertEqual(self.socket.sent["method"], "set_rgb")
        self.assertEqual(self.socket.sent["params"], [16776960, "sudden", 300])

    def test_hsv1(self):
        self.bulb.set_hsv(200, 100, effect="sudden")
        self.assertEqual(self.socket.sent["method"], "set_hsv")
        self.assertEqual(self.socket.sent["params"], [200, 100, "sudden", 300])

    def test_hsv2(self):
        self.bulb.set_hsv(200, 100, 10, effect="sudden", duration=500)
        self.assertEqual(self.socket.sent["method"], "start_cf")
        self.assertEqual(self.socket.sent["params"], [1, 1, "50, 1, 43263, 10"])

    def test_hsv3(self):
        self.bulb.set_hsv(200, 100, 10, effect="smooth", duration=1000)
        self.assertEqual(self.socket.sent["method"], "start_cf")
        self.assertEqual(self.socket.sent["params"], [1, 1, "1000, 1, 43263, 10"])

    def test_hsv4(self):
        self.bulb.effect = "sudden"
        self.bulb.set_hsv(200, 100, 10, effect="smooth", duration=1000)
        self.assertEqual(self.socket.sent["method"], "start_cf")
        self.assertEqual(self.socket.sent["params"], [1, 1, "1000, 1, 43263, 10"])

    def test_toggle1(self):
        self.bulb.toggle()
        self.assertEqual(self.socket.sent["method"], "toggle")
        self.assertEqual(self.socket.sent["params"], ["smooth", 300])

        self.bulb.toggle(duration=3000)
        self.assertEqual(self.socket.sent["params"], ["smooth", 3000])

    def test_turn_off1(self):
        self.bulb.turn_off()
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["off", "smooth", 300])

        self.bulb.turn_off(duration=3000)
        self.assertEqual(self.socket.sent["params"], ["off", "smooth", 3000])

    def test_turn_on1(self):
        self.bulb.turn_on()
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["on", "smooth", 300])

        self.bulb.turn_on(duration=3000)
        self.assertEqual(self.socket.sent["params"], ["on", "smooth", 3000])

    def test_turn_on2(self):
        self.bulb.effect = "sudden"
        self.bulb.turn_on()
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["on", "sudden", 300])

    def test_turn_on3(self):
        self.bulb.turn_on(effect="sudden", duration=50)
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["on", "sudden", 50])

    def test_turn_on4(self):
        self.bulb.power_mode = enums.PowerMode.MOONLIGHT
        self.bulb.turn_on()
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["on", "smooth", 300, enums.PowerMode.MOONLIGHT.value])

    def test_turn_on5(self):
        self.bulb.turn_on(power_mode=enums.PowerMode.MOONLIGHT)
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["on", "smooth", 300, enums.PowerMode.MOONLIGHT.value])

    def test_set_power_mode1(self):
        self.bulb.set_power_mode(enums.PowerMode.MOONLIGHT)
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["on", "smooth", 300, enums.PowerMode.MOONLIGHT.value])

    def test_set_power_mode2(self):
        self.bulb.set_power_mode(enums.PowerMode.NORMAL)
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["on", "smooth", 300, enums.PowerMode.NORMAL.value])

    def test_set_power_mode3(self):
        self.bulb.set_power_mode(enums.PowerMode.LAST)
        self.assertEqual(self.socket.sent["method"], "set_power")
        self.assertEqual(self.socket.sent["params"], ["on", "smooth", 300])

    def test_color_temp1(self):
        self.bulb.set_color_temp(1400)
        self.assertEqual(self.socket.sent["method"], "set_ct_abx")
        self.assertEqual(self.socket.sent["params"], [1700, "smooth", 300])

        self.bulb.set_color_temp(1400, duration=3000)
        self.assertEqual(self.socket.sent["params"], [1700, "smooth", 3000])

    def test_color_temp2(self):
        self.bulb.set_color_temp(8400, effect="sudden")
        self.assertEqual(self.socket.sent["method"], "set_ct_abx")
        self.assertEqual(self.socket.sent["params"], [6500, "sudden", 300])

    def test_color_temp_with_model_declared(self):
        self.bulb._model = "ceiling2"
        self.bulb.set_color_temp(1800)
        self.assertEqual(self.socket.sent["method"], "set_ct_abx")
        self.assertEqual(self.socket.sent["params"], [2700, "smooth", 300])

    def test_start_flow(self):
        transitions = [TemperatureTransition(1700, duration=40000), TemperatureTransition(6500, duration=40000)]
        flow = Flow(count=1, action=Action.stay, transitions=transitions)
        self.bulb.start_flow(flow)
        self.assertEqual(self.socket.sent["method"], "start_cf")
        self.assertEqual(self.socket.sent["params"], [2, 1, "40000, 2, 1700, 100, 40000, 2, 6500, 100"])

    def test_set_scene_color(self):
        self.bulb.set_scene(SceneClass.COLOR, 255, 255, 0, 10)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["color", 16776960, 10])

    def test_set_scene_color_ambilight(self):
        self.bulb.set_scene(SceneClass.COLOR, 255, 255, 0, 10, light_type=LightType.Ambient)
        self.assertEqual(self.socket.sent["method"], "bg_set_scene")
        self.assertEqual(self.socket.sent["params"], ["color", 16776960, 10])

    def test_set_scene_color_temperature(self):
        self.bulb.set_scene(SceneClass.CT, 2000, 15)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["ct", 2000, 15])

    def test_set_scene_hsv(self):
        self.bulb.set_scene(SceneClass.HSV, 200, 100, 10)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["hsv", 200, 100, 10])

    def test_set_scene_color_flow(self):
        transitions = [TemperatureTransition(1700, duration=40000), TemperatureTransition(6500, duration=40000)]
        flow = Flow(count=1, action=Action.stay, transitions=transitions)
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["cf", 2, 1, "40000, 2, 1700, 100, 40000, 2, 6500, 100"])

    def test_set_scene_auto_delay_off(self):
        self.bulb.set_scene(SceneClass.AUTO_DELAY_OFF, 20, 1)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["auto_delay_off", 20, 1])

    def test_sunrise(self):
        flow = flows.sunrise()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(
            self.socket.sent["params"], ["cf", 3, 1, "50, 1, 16731392, 1, 360000, 2, 1700, 10, 540000, 2, 2700, 100"]
        )

    def test_sunset(self):
        flow = flows.sunset()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(
            self.socket.sent["params"], ["cf", 3, 2, "50, 2, 2700, 10, 180000, 2, 1700, 5, 420000, 1, 16731136, 1"]
        )

    def test_romance(self):
        flow = flows.romance()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["cf", 0, 1, "4000, 1, 5838189, 1, 4000, 1, 6689834, 1"])

    def test_happy_birthday(self):
        flow = flows.happy_birthday()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(
            self.socket.sent["params"],
            ["cf", 0, 1, "1996, 1, 14438425, 80, 1996, 1, 14448670, 80, 1996, 1, 11153940, 80"],
        )

    def test_candle_flicker(self):
        flow = flows.candle_flicker()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(
            self.socket.sent["params"],
            [
                "cf",
                0,
                0,
                "800, 2, 2700, 50, 800, 2, 2700, 30, 1200, 2, 2700, 80, 800, 2, 2700, 60, 1200, 2, 2700, 90, 2400, 2, 2700, 50, 1200, 2, 2700, 80, 800, 2, 2700, 60, 400, 2, 2700, 70",
            ],
        )

    def test_home(self):
        flow = flows.home()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["cf", 0, 0, "500, 2, 3200, 80"])

    def test_night_mode(self):
        flow = flows.night_mode()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["cf", 0, 0, "500, 1, 16750848, 1"])

    def test_date_night(self):
        flow = flows.date_night()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["cf", 0, 0, "500, 1, 16737792, 50"])

    def test_movie(self):
        flow = flows.movie()
        self.bulb.set_scene(SceneClass.CF, flow)
        self.assertEqual(self.socket.sent["method"], "set_scene")
        self.assertEqual(self.socket.sent["params"], ["cf", 0, 0, "500, 1, 1315890, 50"])

    def test_notification(self):
        notification_event = threading.Event()
        listening_stopped_event = threading.Event()
        shutdown = False

        def _callback(new_properties):
            notification_event.set()

        def _listen():
            self.bulb.listen(_callback)
            listening_stopped_event.set()

        def _blocking_recv(size):
            time.sleep(0.1)
            if shutdown:
                raise IOError
            return b'{"method": "props", "params": {"power": "on"}}'

        def _shutdown(type):
            shutdown = True  # noqa: F841

        socket = mock.MagicMock()
        type(socket).recv = mock.MagicMock(side_effect=_blocking_recv)
        type(socket).shutdown = mock.MagicMock(side_effect=_shutdown)

        with mock.patch("yeelight.main.socket.socket", return_value=socket):
            assert self.bulb.last_properties == {}
            thread = threading.Thread(target=_listen)
            thread.start()
            assert notification_event.wait(0.5) is True
            assert self.bulb.last_properties == {"power": "on"}
            self.bulb.stop_listening()
            assert listening_stopped_event.wait(0.5) is True


if __name__ == "__main__":
    unittest.main()
