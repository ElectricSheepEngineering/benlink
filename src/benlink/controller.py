"""
# Overview

This module provides a high-level async interface for communicating
with and controlling Benshi radios over BLE.

# Examples

To run the examples below, you will need to pair your radio with your computer,
locate the radio's device UUID (e.g. `XX:XX:XX:XX:XX:XX`), and substitute it
into the example code.

## Connecting To The Device

The following will connect to a radio and print its device info:

```python
import asyncio
from benlink.controller import RadioController

async def main():
    async with RadioController.new_ble("XX:XX:XX:XX:XX:XX") as radio:
        print(radio.device_info)

asyncio.run(main())
```

You can also connect to the radio over RFCOMM:

```python
import asyncio
from benlink.controller import RadioController

async def main():
    async with RadioController.new_rfcomm("XX:XX:XX:XX:XX:XX", channel=1) as radio:
        print(radio.device_info)

asyncio.run(main())
```

At the present, you have to figure out the correct channel number yourself (in Linux,
you can get a list of the available channels by running `sdptool records XX:XX:XX:XX:XX:XX`).
Planned support of channel autodetection can be tracked in [this issue](https://github.com/khusmann/benlink/issues/9).

## Changing Settings

The following will connect to a radio and change the name of the first channel:

```python
import asyncio
from benlink.controller import RadioController


async def main():
    async with RadioController.new_ble("XX:XX:XX:XX:XX:XX") as radio:
        print(f"Channel 0 name: {radio.channels[0].name}")
        print("Setting 0 name to Foo...")
        await radio.set_channel(0, name="Foo")
        print("Done")

asyncio.run(main())
```

## Handling Events

The `RadioController` class provides a `add_event_handler` method for
registering a callback function to handle events. The callback function
will be called with an `EventMessage` object whenever an event is
received from the radio.

Note that `add_event_handler` returns a function that can be called
to unregister the event handler.

```python
import asyncio
from benlink.controller import RadioController

async def main():
    async with RadioController.new_ble("XX:XX:XX:XX:XX:XX") as radio:
        def handle_event(event):
            print(f"Received event: {event}")

        unregister = radio.add_event_handler(handle_event)

        print("Try changing the channel or updating a radio setting")
        print()
        print("Press enter to quit...")
        await asyncio.to_thread(input)

asyncio.run(main())
```

# Interactive Usage

Python's async REPL is a great tool for interactively exploring the radio's
capabilities. To run Python's REPL in async mode, run:

```bash
python -m asyncio
```

Instead of using the async context manager (`async with RadioController(...) as radio:`),
you can use `await radio.connect()` and `await radio.disconnect()` to manage the
connection manually:

```python
from benlink.controller import RadioController

radio = RadioController.new_ble("XX:XX:XX:XX:XX:XX")

await radio.connect()

print(radio.device_info) # Prints device info

print(await radio.battery_voltage()) # Prints battery voltage

await radio.disconnect() # When you're done with your session disconnect nicely
```

Events registered with `add_event_handler` will run in the background:

```python
import asyncio
from benlink.controller import RadioController

radio = RadioController.new_ble("XX:XX:XX:XX:XX:XX")

await radio.connect()

unsubscribe = radio.add_event_handler(lambda x: print(f"Received event: {x}\n"))

# Change the channel on the radio a few times to generate some events

unsubscribe() # Unsubscribe the event handler

# Change the channel on the radio a few times to generate some events and
# observe that the event handler is no longer called

await radio.disconnect() # When you're done with your session disconnect nicely
```

(Note for IPython users: The IPython async REPL blocks the async event
loop while waiting for a prompt, so events will queue up until you defer 
execution to the event loop by running something like `await asyncio.sleep(0)`.)
"""


from __future__ import annotations
from typing_extensions import Unpack
from dataclasses import dataclass
import typing as t
import logging

from . import protocol as p
from .command import (
    CommandConnection,
    EventHandler,
    DeviceInfo,
    Channel,
    ChannelArgs,
    Settings,
    SettingsArgs,
    BeaconSettings,
    BeaconSettingsArgs,
    TncDataFragment,
    EventMessage,
    EventType,
    SettingsChangedEvent,
    TncDataFragmentReceivedEvent,
    ChannelChangedEvent,
    StatusChangedEvent,
    UnknownProtocolMessage,
    Status,
    Position,
)


logger = logging.getLogger(__name__)


@dataclass
class _RadioState:
    device_info: DeviceInfo
    beacon_settings: BeaconSettings
    status: Status
    settings: Settings
    channels: t.List[Channel]


class RadioController:
    _conn: CommandConnection
    _state: _RadioState | None

    def __init__(self, connection: CommandConnection):
        self._conn = connection
        self._state = None

    @classmethod
    def new_ble(cls, device_uuid: str) -> RadioController:
        return RadioController(CommandConnection.new_ble(device_uuid))

    @classmethod
    def new_rfcomm(cls, device_uuid: str, channel: int | t.Literal["auto"] = "auto") -> RadioController:
        return RadioController(CommandConnection.new_rfcomm(device_uuid, channel))

    def __repr__(self):
        if not self.is_connected():
            return f"<{self.__class__.__name__} (disconnected)>"
        return f"<{self.__class__.__name__} (connected)>"

    @property
    def beacon_settings(self) -> BeaconSettings:
        if self._state is None:
            raise StateNotInitializedError()
        return self._state.beacon_settings

    async def set_beacon_settings(self, **packet_settings_args: Unpack[BeaconSettingsArgs]):
        if self._state is None:
            raise StateNotInitializedError()

        new_beacon_settings = self._state.beacon_settings.model_copy(
            update=dict(packet_settings_args)
        )

        await self._conn.set_beacon_settings(new_beacon_settings)

        self._state.beacon_settings = new_beacon_settings

    @property
    def status(self) -> Status:
        if self._state is None:
            raise StateNotInitializedError()
        return self._state.status

    @property
    def settings(self) -> Settings:
        if self._state is None:
            raise StateNotInitializedError()
        return self._state.settings

    async def set_settings(self, **settings_args: Unpack[SettingsArgs]):
        if self._state is None:
            raise StateNotInitializedError()

        new_settings = self._state.settings.model_copy(
            update=dict(settings_args)
        )

        await self._conn.set_settings(new_settings)

        self._state.settings = new_settings

        # Poll status multiple times after scan toggle to catch transient states
        if 'scan' in settings_args:
            import asyncio
            for delay in (0.2, 0.5, 1.0, 2.0):
                await asyncio.sleep(delay)
                status = await self._conn.get_status()
                logger.debug(
                    "[SET_SETTINGS] t+%.1fs status: is_scan=%s, "
                    "is_power_on=%s, is_radio=%s, double_channel=%s, "
                    "curr_ch_id=%s, is_rx=%s, is_sq=%s",
                    delay, status.is_scan,
                    status.is_power_on, status.is_radio,
                    status.double_channel, status.curr_ch_id,
                    status.is_in_rx, status.is_sq
                )
                self._state.status = status
                if status.is_scan:
                    break  # Scan started, no need to poll more

    async def set_region(self, region_id: int) -> None:
        """Switch the active region (memory bank) and reload channels."""
        if self._state is None:
            raise StateNotInitializedError()

        await self._conn.set_region(region_id)

        # Reload channels from the new region
        channels: t.List[Channel] = []
        for i in range(self._state.device_info.channel_count):
            try:
                ch = await self._conn.get_channel(i)
                channels.append(ch)
            except Exception:
                break

        self._state.channels = channels

    @property
    def device_info(self) -> DeviceInfo:
        if self._state is None:
            raise StateNotInitializedError()
        return self._state.device_info

    @property
    def channels(self) -> t.List[Channel]:
        if self._state is None:
            raise StateNotInitializedError()
        return self._state.channels

    async def set_channel(
        self, channel_id: int, **channel_args: Unpack[ChannelArgs]
    ):
        if self._state is None:
            raise StateNotInitializedError()

        new_channel = self._state.channels[channel_id].model_copy(
            update=dict(channel_args)
        )

        await self._conn.set_channel(new_channel)

        self._state.channels[channel_id] = new_channel

    def is_connected(self) -> bool:
        return self._state is not None and self._conn.is_connected()

    async def send_bytes(self, command: bytes) -> None:
        """For debugging - Use at your own risk!"""
        await self._conn.send_bytes(command)

    async def set_volume(self, level: int) -> None:
        """Set hardware volume (0-15) using dedicated SET_VOLUME command."""
        await self._conn.set_volume(level)

    async def get_volume(self) -> int:
        """Get hardware volume (0-15) using dedicated GET_VOLUME command."""
        return await self._conn.get_volume()

    async def set_scan(self, enabled: bool) -> None:
        """Toggle scan using dedicated SET_IN_SCAN command."""
        await self._conn.set_scan(enabled)

    async def set_power(self, on: bool) -> None:
        """Power the radio HT on or off."""
        await self._conn.set_power_on_off(on)

    async def fm_radio_set_mode(self, mode: int) -> None:
        """Set FM broadcast radio mode (0=off, 1=on)."""
        await self._conn.fm_radio_set_mode(mode)

    async def fm_radio_seek_up(self) -> None:
        """Seek up on FM broadcast band."""
        await self._conn.fm_radio_seek_up()

    async def fm_radio_seek_down(self) -> None:
        """Seek down on FM broadcast band."""
        await self._conn.fm_radio_seek_down()

    async def fm_radio_set_freq(self, freq_khz: int) -> None:
        """Set FM broadcast radio frequency in kHz (e.g. 101500 for 101.5 MHz)."""
        await self._conn.fm_radio_set_freq(freq_khz)

    async def play_tone(self, tone_id: int) -> None:
        """Play a tone on the radio."""
        await self._conn.play_tone(tone_id)

    async def stop_ringing(self) -> None:
        """Stop any ringing/alert tone."""
        await self._conn.stop_ringing()

    async def set_time(self, timestamp: int) -> None:
        """Set radio clock (Unix epoch seconds)."""
        await self._conn.set_time(timestamp)

    async def battery_voltage(self) -> float:
        return await self._conn.get_battery_voltage()

    async def battery_level(self) -> int:
        return await self._conn.get_battery_level()

    async def battery_level_as_percentage(self) -> int:
        return await self._conn.get_battery_level_as_percentage()

    async def rc_battery_level(self) -> int:
        return await self._conn.get_rc_battery_level()

    async def position(self) -> Position:
        return await self._conn.get_position()

    async def get_aprs_path(self) -> str:
        """Get the APRS digipeater path from the radio (e.g. 'WIDE1-1,WIDE2-1')."""
        return await self._conn.get_aprs_path()

    async def set_aprs_path(self, path: str) -> None:
        """Set the APRS digipeater path on the radio (e.g. 'WIDE1-1,WIDE2-1')."""
        await self._conn.set_aprs_path(path)

    async def send_tnc_data(self, data: bytes, channel_id: int | None = None) -> None:
        MAX_FRAGMENT_SIZE = 50  # Matches HTCommander's MAX_MTU for BLE
        offset = 0
        fragment_id = 0
        while offset < len(data):
            chunk = data[offset:offset + MAX_FRAGMENT_SIZE]
            is_last = (offset + len(chunk)) >= len(data)
            await self._conn.send_tnc_data_fragment(TncDataFragment(
                is_final_fragment=is_last,
                fragment_id=fragment_id & 0x3F,  # 6-bit field
                data=chunk,
                channel_id=channel_id
            ))
            offset += len(chunk)
            fragment_id += 1

    def add_event_handler(self, handler: EventHandler) -> t.Callable[[], None]:
        return self._conn.add_event_handler(handler)

    async def enable_event(self, event_type: EventType):
        await self._conn.enable_event(event_type)

    async def _hydrate(self) -> None:
        device_info = await self._conn.get_device_info()

        channels: t.List[Channel] = []

        total_channels = device_info.channel_count
        for i in range(total_channels):
            try:
                channel_settings = await self._conn.get_channel(i)
            except ValueError:
                # Radio rejected this channel index (INVALID_PARAMETER).
                # Some radios/firmware versions don't support the full
                # advertised channel range. Stop reading and continue
                # with what we have.
                logger.warning(
                    "get_channel(%d) failed, stopping at %d channels "
                    "(radio advertised %d)",
                    i, len(channels), total_channels
                )
                break
            channels.append(channel_settings)

        settings = await self._conn.get_settings()

        beacon_settings = await self._conn.get_beacon_settings()

        status = await self._conn.get_status()

        # For some reason, enabling the HT_STATUS_CHANGED event
        # also enables the DATA_RXD event, and maybe others...
        # need to investigate further.
        await self.enable_event("HT_STATUS_CHANGED")

        # TODO: should these events be enabled by default? perhaps I should have
        # users enable events manually, while simultaneously registering handlers
        # of the proper type?

        self._state = _RadioState(
            device_info=device_info,
            beacon_settings=beacon_settings,
            status=status,
            settings=settings,
            channels=channels,
        )

        # No need to save the remove event handler function, since we don't
        # need to unregister it when we disconnect (the connection will take care of that)
        self._conn.add_event_handler(
            self._on_event_message
        )

    def _on_event_message(self, event_message: EventMessage) -> None:
        if self._state is None:
            raise ValueError(
                "Radio state not initialized. Try calling connect() first."
            )

        match event_message:
            case ChannelChangedEvent(channel):
                self._state.channels[channel.channel_id] = channel
            case SettingsChangedEvent(settings):
                self._state.settings = settings
            case TncDataFragmentReceivedEvent():
                pass
            case StatusChangedEvent(status):
                self._state.status = status
            case UnknownProtocolMessage(message):
                # Suppress noisy debug for known unsolicited messages
                if (message.command_group == p.CommandGroup.EXTENDED or
                    message.command in (
                        p.BasicCommand.GET_VOLUME,
                        p.BasicCommand.SET_VOLUME,
                        p.BasicCommand.SET_IN_SCAN,
                    )):
                    pass  # Handled by dedicated handlers or benign
                else:
                    logger.debug("Unknown protocol message: %s", message)

    # Async Context Manager
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: t.Any,
        exc_value: t.Any,
        traceback: t.Any,
    ) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        if self._state is not None:
            raise RuntimeError("Already connected")

        await self._conn.connect()
        await self._hydrate()

    async def disconnect(self) -> None:
        if self._state is None:
            raise StateNotInitializedError()

        await self._conn.disconnect()
        self._state = None


class StateNotInitializedError(RuntimeError):
    """Raised when trying to access radio state before it has been initialized."""

    def __init__(self):
        super().__init__(
            "Radio state not initialized. Try calling connect() first."
        )
