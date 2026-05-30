"""Background BLE client that receives gesture labels from the conductor wand."""

from __future__ import annotations

import asyncio
import logging
import threading

LOGGER = logging.getLogger(__name__)

_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
_DEVICE_NAME = "ConductorWand"
_RETRY_DELAY = 3.0


class WandController:
    """Connects to the ESP32 wand over BLE and forwards gestures to the mixer UI."""

    def __init__(self, ui) -> None:
        self._ui = ui
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="WandBLE", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_loop())
        finally:
            self._loop.close()

    async def _connect_loop(self) -> None:
        from bleak import BleakClient, BleakScanner

        while True:
            try:
                LOGGER.info("Scanning for %s...", _DEVICE_NAME)
                device = await BleakScanner.find_device_by_name(_DEVICE_NAME, timeout=10.0)
                if device is None:
                    LOGGER.info("%s not found, retrying in %.0fs", _DEVICE_NAME, _RETRY_DELAY)
                    await asyncio.sleep(_RETRY_DELAY)
                    continue

                LOGGER.info("Connecting to %s...", _DEVICE_NAME)
                async with BleakClient(device) as client:
                    LOGGER.info("Wand connected")
                    await client.start_notify(_TX_CHAR_UUID, self._on_gesture)
                    while client.is_connected:
                        await asyncio.sleep(1.0)
                LOGGER.info("Wand disconnected, reconnecting...")

            except Exception as exc:
                LOGGER.warning("Wand BLE error: %s, retrying in %.0fs", exc, _RETRY_DELAY)
                await asyncio.sleep(_RETRY_DELAY)

    def _on_gesture(self, _sender, data: bytearray) -> None:
        gesture = data.decode(errors="ignore").strip()
        LOGGER.info("Wand gesture: %s", gesture)
        self._ui.apply_wand_gesture(gesture)
