"""
WIN_HWID — hardware fingerprint для лицензирования (Windows-only).

Зеркалит GetVolumeInformationW + GetAdaptersInfo из follow.exe:
серийный номер диска C: + MAC первого адаптера → уникальный HWID.

get_hwid() → str (16 hex символов)
"""
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
import hashlib
import struct

kernel32 = ctypes.windll.kernel32
iphlpapi = ctypes.windll.iphlpapi


# ---------------------------------------------------------------- volume serial

def get_volume_serial(root: str = "C:\\") -> str:
    """Серийный номер тома (GetVolumeInformationW)."""
    serial   = wt.DWORD()
    vol_name = ctypes.create_unicode_buffer(256)
    fs_name  = ctypes.create_unicode_buffer(256)
    ok = kernel32.GetVolumeInformationW(
        root, vol_name, 256,
        ctypes.byref(serial), None, None,
        fs_name, 256,
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    return f"{serial.value:08X}"


# ---------------------------------------------------------------- MAC address

class IP_ADAPTER_INFO(ctypes.Structure):
    pass

IP_ADAPTER_INFO._fields_ = [
    ("Next",                ctypes.POINTER(IP_ADAPTER_INFO)),
    ("ComboIndex",          wt.DWORD),
    ("AdapterName",         ctypes.c_char * 260),
    ("Description",         ctypes.c_char * 132),
    ("AddressLength",       wt.UINT),
    ("Address",             ctypes.c_ubyte * 8),
    ("Index",               wt.DWORD),
    ("Type",                wt.UINT),
    ("DhcpEnabled",         wt.UINT),
    ("CurrentIpAddress",    ctypes.c_void_p),
    ("IpAddressList",       ctypes.c_byte * 64),
    ("GatewayList",         ctypes.c_byte * 64),
    ("DhcpServer",          ctypes.c_byte * 64),
    ("HaveWins",            wt.BOOL),
    ("PrimaryWinsServer",   ctypes.c_byte * 64),
    ("SecondaryWinsServer", ctypes.c_byte * 64),
    ("LeaseObtained",       ctypes.c_long),
    ("LeaseExpires",        ctypes.c_long),
]


def get_mac_address() -> str:
    """MAC-адрес первого сетевого адаптера (GetAdaptersInfo)."""
    size = wt.ULONG(0)
    iphlpapi.GetAdaptersInfo(None, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    ret = iphlpapi.GetAdaptersInfo(buf, ctypes.byref(size))
    if ret != 0:
        return "000000000000"
    adapter = IP_ADAPTER_INFO.from_buffer_copy(buf)
    mac_bytes = bytes(adapter.Address[:adapter.AddressLength])
    return mac_bytes.hex().upper()


# ---------------------------------------------------------------- HWID

def get_hwid() -> str:
    """Возвращает 16-символьный fingerprint: sha256(serial+mac)[:16].upper()"""
    try:
        serial = get_volume_serial()
    except OSError:
        serial = "00000000"
    try:
        mac = get_mac_address()
    except Exception:
        mac = "000000000000"
    raw = f"{serial}{mac}".encode()
    return hashlib.sha256(raw).hexdigest()[:16].upper()


if __name__ == "__main__":
    print(f"Volume serial : {get_volume_serial()}")
    print(f"MAC address   : {get_mac_address()}")
    print(f"HWID          : {get_hwid()}")
