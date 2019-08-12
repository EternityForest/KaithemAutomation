class UPnPErrorCodeDescriptions(object):
    _descriptions = {
        401: 'No action by that name at this service.',
        402: ('Could be any of the following: not enough in args, args in the wrong order, one or m'
              'ore in args are of the wrong data type.'),
        403: '(Deprecated - no not use)',
        501: 'MAY be returned if current state of service prevents invoking that action.',
        600: 'The argument value is invalid',
        601: ('An argument value is less than the minimum or more than the maximum value of the all'
              'owed value range, or is not in the allowed value list.'),
        602: 'The requested action is optional and is not implemented by the device.',
        603: ('The device does not have sufficient memory available to complete the action. This MA'
              'Y be a temporary condition; the control point MAY choose to retry the unmodified req'
              'uest again later and it MAY succeed if memory is available.'),
        604: ('The device has encountered an error condition which it cannot resolve itself and req'
              'uired human intervention such as a reset or power cycle. See the device display or d'
              'ocumentation for further guidance.'),
        605: 'A string argument is too long for the device to handle properly.'
    }

    def __getitem__(self, key):
        if not isinstance(key, int):
            raise KeyError("'key' must be an integer")
        if 606 <= key <= 612:
            return 'These ErrorCodes are reserved for UPnP DeviceSecurity.'
        elif 613 <= key <= 699:
            return 'Common action errors. Defined by UPnP Forum Technical Committee.'
        elif 700 <= key <= 799:
            return 'Action-specific errors defined by UPnP Forum working committee.'
        elif 800 <= key <= 899:
            return 'Action-specific errors for non-standard actions. Defined by UPnP vendor.'
        return self._descriptions[key]


ERR_CODE_DESCRIPTIONS = UPnPErrorCodeDescriptions()
