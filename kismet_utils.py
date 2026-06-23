"""
Helpers for reading Kismet device records.
"""
import json
from typing import Any, Dict, List

DOT11_DEVICE_KEY = 'dot11.device'
LAST_PROBED_SSID_RECORD_KEY = 'dot11.device.last_probed_ssid_record'
PROBED_SSID_KEY = 'dot11.probedssid.ssid'


def _coerce_device_data(device_record: Any) -> Dict[str, Any]:
    """Return a Kismet device dict from a decoded dict or JSON string."""
    if isinstance(device_record, str):
        try:
            device_record = json.loads(device_record)
        except (json.JSONDecodeError, TypeError):
            return {}

    if isinstance(device_record, dict):
        return device_record

    return {}


def get_last_probed_ssid(device_record: Any) -> str:
    """Extract the last probed SSID from a Kismet device record."""
    device_data = _coerce_device_data(device_record)
    dot11_device = device_data.get(DOT11_DEVICE_KEY, {})
    if not isinstance(dot11_device, dict):
        return ''

    probe_record = dot11_device.get(LAST_PROBED_SSID_RECORD_KEY, {})
    if not isinstance(probe_record, dict):
        return ''

    ssid = probe_record.get(PROBED_SSID_KEY, '')
    if isinstance(ssid, str):
        return ssid

    return ''


def get_last_probed_ssids(device_record: Any) -> List[str]:
    """Extract the last probed SSID as the list shape used by surveillance records."""
    ssid = get_last_probed_ssid(device_record)
    return [ssid] if ssid else []
