class MQTTInterface:
    """Replace this transport when your ESP32 broker and topics are ready."""
    async def command(self, device: str, action: str) -> str:
        # TODO: connect an MQTT client; configure broker, topic allowlist and QoS.
        # TODO: wait for device acknowledgement; never claim success before it arrives.
        return f'MQTT is not connected yet. I have not performed {action} on {device}.'
