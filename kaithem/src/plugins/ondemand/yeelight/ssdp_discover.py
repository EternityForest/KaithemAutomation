import socket

import ifaddr


def get_ip_address(ifname):
    """
    Return the first IPv4 address of the requested interface.

    :param string interface: The interface to get the IPv4 address of.

    :returns: The interface's IPv4 address.

    """
    for adapter in ifaddr.get_adapters():
        if adapter.name != ifname:
            continue
        for ip in adapter.ips:
            if not isinstance(ip.ip, tuple):  # not IPv6
                return ip.ip
    return None


def send_discovery_packet(timeout=2, interface=False, ip_address="239.255.255.250"):
    """
    Send SSDP discovery packet.

    :param int timeout: How many seconds to wait for replies. Discovery will
                        always take exactly this long to run, as it can't know
                        when all the bulbs have finished responding.
    :param string interface: The interface that should be used for multicast packets.
                             Note: it *has* to have a valid IPv4 address. IPv6-only
                             interfaces are not supported (at the moment).
                             The default one will be used if this is not specified.
    :param string ip_address: IP address to send ssdp discovery packet to. If provided, it will be send to specified
                              device. Otherwise it will be sent to the multicast address.

    :return: Socket used to send packet.

    """
    msg = "\r\n".join(["M-SEARCH * HTTP/1.1", "HOST: " + ip_address + ":1982", 'MAN: "ssdp:discover"', "ST: wifi_bulb"])

    # Set up the UDP socket.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
    if interface:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(get_ip_address(interface)))
    s.settimeout(timeout)
    s.sendto(msg.encode(), (ip_address, 1982))

    return s


def parse_capabilities(data):
    """
    Parse SSDP discovery capabilities to a dictionary.

    :param string data: Original data from SSDP discovery from the bulb.

    Example:
    'HTTP/1.1 200 OK
    Cache-Control: max-age=3600
    Date:
    Ext:
    Location: yeelight://10.0.7.184:55443
    Server: POSIX UPnP/1.0 YGLC/1
    id: 0x00000000037073d2
    model: color
    fw_ver: 76
    ...'

    :return: Parsed response as dict.

    Example:
    {
        'Location': 'yeelight://10.0.7.184:55443',
        'Server': 'POSIX UPnP/1.0 YGLC/1',
        'id': '0x00000000037073d2',
        'model': 'color',
        'fw_ver': '76',
        ...
    }
    """
    return dict([x.strip("\r").split(": ") for x in data.decode().split("\n") if ":" in x])


def filter_lower_case_keys(dict):
    """
    Filter dict to include only lower case keys.

    Used to skip HTTP response fields.

    :param dict: Dict with all capabilities parsed from the SSDP discovery.

    :return: Dict with lower case keys only.
    """
    return {key: value for key, value in dict.items() if key.islower()}
