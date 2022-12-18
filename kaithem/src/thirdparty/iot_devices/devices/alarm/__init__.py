from iot_devices import device


class ConfigurableAlarm(device.Device):
    """
        This class is just a simple wrapper for your framework's alarm functionality.
    """
    device_type = "ConfigurableAlarm"

    def __init__(self, name, data, **kw):
        device.Device.__init__(self, name, data, **kw)

        self.set_config_default("device.alarm_name", "alarm")
        self.set_config_default("device.priority", "warning")
        self.set_config_default("device.auto_acknowledge", "no")

        # When this is a 1, we alarm.
        self.numeric_data_point("trigger")

        self.set_alarm(self.config['device.alarm_name'],
                       "trigger",
                       expression="value>0.5",
                       priority=self.config['device.priority'],
                       autoAck=self.config['device.auto_acknowledge'].lower()
                       in ('yes', 'true'))
