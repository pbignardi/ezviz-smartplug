"""Platform for EZVIZ Smart Plug integration."""

from __future__ import annotations

import logging

# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from pyezvizapi import client

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


def get_plugs(client: client.EzvizClient):
    """Retrieve device informations. This performs I/O, should be async."""
    devs = client.get_device_infos()
    plugs = []
    for device in devs:
        plugs.append(devs[device])
    return tuple(plugs)


def get_plug(client: client.EzvizClient, target_serial: str):
    all_plugs = get_plugs(client)
    for dev in all_plugs:
        if dev["deviceInfos"]["deviceSerial"] == target_serial:
            return dev

    raise Exception("No devices found")


def parse_plug_data(plug: dict):
    # name of the plug
    name = None
    # serial of the plug
    serial = None
    # state of the plug (on/off)
    state = None
    # plug is online
    online_status = None

    if "resourceInfos" in plug:
        resourceInfos = plug["resourceInfos"]
        name = resourceInfos["resourceName"]
        serial = resourceInfos["deviceSerial"]

    if "SWITCH" in plug:
        switch = plug["SWTITCH"]
        switch_states = [data["enable"] for data in switch if data["type"] == 14]
        state = switch_states[0] if switch_states else None

    if "STATUS" in plug:
        if "optionals" in plug["STATUS"]:
            if "OnlineStatus" in plug["STATUS"]["optionals"]:
                online_status = plug["STATUS"]["optionals"]["OnlineStatus"]

    return name, serial, state, online_status


def get_plug_data(client: client.EzvizClient, target_serial: str):
    plug = get_plug(client, target_serial)
    return parse_plug_data(plug)


def set_plug_state(client: client.EzvizClient, target_serial: str, state: int):
    client.switch_status(target_serial, 14, state)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the EZVIZ Smart Plug platform."""
    # retrieve configuration parameters
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    if not username or not password:
        _LOGGER.warning("Missing username/email and password in configuration")
        return

    # create client to connect to EZVIZ API
    ezclient = client.EzvizClient(username, password)
    token = ezclient.login()

    # Verify that response is valid and login succeeded
    if not token:
        _LOGGER.error("Unsuccessful connection to EZVIZ API")
        return

    # retrieve all plugs from ezclient
    plugs = get_plugs(ezclient)
    names = []
    serials = []
    states = []

    for plug in plugs:
        name, serial, state, _ = parse_plug_data(plug)
        names.append(name)
        serials.append(serial)
        states.append(state)

    _LOGGER.info("Retrieved all plugs in EZVIZ")

    # Add devices
    add_entities(
        EZPlug(name, serial, state, ezclient)
        for name, serial, state in zip(names, serials, states)
    )


class EZPlug(SwitchEntity):
    """Representation of an EZVIZ Smart Plug."""

    def __init__(
        self, name: str, serial: str, state: int, client: client.EzvizClient
    ) -> None:
        """Initialize an AwesomeLight."""
        self._name = name
        self._serial = serial
        self._client = client
        self._state = state

    @property
    def serial(self):
        """Return serial of the plug."""
        return self._serial

    @property
    def client(self):
        """Return the EZVIZ client."""
        return self._client

    @property
    def name(self):
        """Return the display name of this plug."""
        return self._name

    @property
    def is_on(self):
        """Return the state of the plug (on/off).

        True if the plug is on, False if the plug is off.
        """
        return self._state == 1

    def turn_on(self, **kwargs):
        """Instruct the switch to turn on."""
        if not self.is_on:
            set_plug_state(self._client, self._serial, 1)

    def turn_off(self, **kwargs):
        """Instruct the switch to turn off."""
        if self.is_on:
            set_plug_state(self._client, self._serial, 0)

    def update(self):
        """Update data for this plug based on serial."""
        name, _, state, _ = get_plug_data(self.client, self.serial)
        self._name = name
        self._state = state
