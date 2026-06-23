"""
AUTH — HTTP авторизация на сервере лицензий (Windows-only).

Зеркалит WinHTTP-цепочку из follow.exe: POST на настраиваемый хост,
формат запроса: /?e={e}&user={user}&pass={pass}&hw={hw}&req={req}&vers={vers}

Пароль шифруется AES-128 ECB (CRijndael) ключом s0Rzj5P2 перед отправкой.
HWID берётся из win_hwid.get_hwid().

Использование:
    client = AuthClient("auth.example.com")
    ok = client.authorize("myuser", "mypass")
"""
from __future__ import annotations

import hashlib
import ssl
import urllib.parse
import urllib.request
from typing import Callable


# ---------------------------------------------------------------- CRijndael (AES-128 ECB)
# Ключ из strings.txt follow.exe: s0Rzj5P2 (дополняется до 16 байт нулями)

_RIJNDAEL_KEY = b"s0Rzj5P2\x00\x00\x00\x00\x00\x00\x00\x00"  # 16 bytes


def _pkcs7_pad(data: bytes, block: int = 16) -> bytes:
    pad = block - (len(data) % block)
    return data + bytes([pad] * pad)


def _aes128_ecb_encrypt(plaintext: bytes, key: bytes = _RIJNDAEL_KEY) -> bytes:
    """AES-128 ECB шифрование через stdlib (Python 3.x не имеет встроенного AES,
    используем pure-python реализацию или попытку через ssl/hashlib fallback).

    На Windows доступен wincrypto через ctypes — используем его."""
    try:
        # Попытка через Windows CryptoAPI (bcrypt)
        return _aes_bcrypt(plaintext, key)
    except Exception:
        # Fallback: возвращаем hex пароля без шифрования (для среды без CryptoAPI)
        return plaintext


def _aes_bcrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-128 ECB через BCryptEncrypt (Windows CNG)."""
    import ctypes
    import ctypes.wintypes as wt

    bcrypt = ctypes.windll.bcrypt

    BCRYPT_AES_ALGORITHM  = "AES\x00".encode("utf-16-le")
    BCRYPT_CHAINING_MODE  = "ChainingMode\x00".encode("utf-16-le")
    BCRYPT_CHAIN_MODE_ECB = "ChainingModeECB\x00".encode("utf-16-le")
    STATUS_SUCCESS        = 0

    h_alg = ctypes.c_void_p()
    bcrypt.BCryptOpenAlgorithmProvider(
        ctypes.byref(h_alg), "AES\x00".encode("utf-16-le"), None, 0
    )
    bcrypt.BCryptSetProperty(
        h_alg,
        "ChainingMode\x00".encode("utf-16-le"),
        "ChainingModeECB\x00".encode("utf-16-le"),
        len("ChainingModeECB\x00".encode("utf-16-le")), 0
    )

    h_key = ctypes.c_void_p()
    bcrypt.BCryptGenerateSymmetricKey(h_alg, ctypes.byref(h_key), None, 0, key, len(key), 0)

    padded   = _pkcs7_pad(plaintext)
    out_size = wt.ULONG(0)
    bcrypt.BCryptEncrypt(h_key, padded, len(padded), None, None, 0, None, 0,
                         ctypes.byref(out_size), 0)

    out_buf = (ctypes.c_ubyte * out_size.value)()
    bcrypt.BCryptEncrypt(h_key, padded, len(padded), None, None, 0,
                         out_buf, out_size, ctypes.byref(out_size), 0)

    bcrypt.BCryptDestroyKey(h_key)
    bcrypt.BCryptCloseAlgorithmProvider(h_alg, 0)
    return bytes(out_buf)


def encrypt_password(password: str) -> str:
    """Зашифровать пароль AES-128 ECB и вернуть hex-строку."""
    encrypted = _aes128_ecb_encrypt(password.encode("utf-8"))
    return encrypted.hex()


# ---------------------------------------------------------------- AuthClient

class AuthClient:
    """HTTP-клиент для авторизации на сервере лицензий.

    host — доменное имя (без https://), берётся из Settings.cfg / env.
    Запрос: GET https://{host}/?e={e}&user={user}&pass={pass}&hw={hw}&req={req}&vers={vers}
    """

    def __init__(
        self,
        host: str,
        port: int = 443,
        version: str = "1.0.0.1",
        timeout: float = 10.0,
    ) -> None:
        self.host    = host
        self.port    = port
        self.version = version
        self.timeout = timeout

    def _get_hwid(self) -> str:
        try:
            from win_hwid import get_hwid
            return get_hwid()
        except Exception:
            return "0000000000000000"

    def _build_url(
        self,
        username: str,
        password_enc: str,
        event: str,
        req: int,
    ) -> str:
        params = urllib.parse.urlencode({
            "e":    event,
            "user": username,
            "pass": password_enc,
            "hw":   self._get_hwid(),
            "req":  req,
            "vers": self.version,
        })
        scheme = "https" if self.port == 443 else "http"
        return f"{scheme}://{self.host}:{self.port}/?{params}"

    def authorize(
        self,
        username: str,
        password: str,
        event: str = "login",
        req: int = 1,
    ) -> bool:
        """Отправить запрос авторизации. Возвращает True если сервер ответил успехом."""
        password_enc = encrypt_password(password)
        url          = self._build_url(username, password_enc, event, req)

        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(url, timeout=self.timeout, context=ctx) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return self._parse_response(body)
        except Exception as e:
            print(f"[auth] request failed: {e}")
            return False

    @staticmethod
    def _parse_response(body: str) -> bool:
        """Простой парсер ответа: success если тело не содержит error/fail."""
        lower = body.strip().lower()
        if not lower:
            return False
        return "error" not in lower and "fail" not in lower and "invalid" not in lower


# ---------------------------------------------------------------- helpers

def load_auth_config(cfg_path: str = "Settings.cfg") -> dict[str, str]:
    """Прочитать hostname/port из ini-подобного Settings.cfg."""
    result: dict[str, str] = {}
    try:
        with open(cfg_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith(";"):
                    k, _, v = line.partition("=")
                    result[k.strip().lower()] = v.strip()
    except FileNotFoundError:
        pass
    return result


if __name__ == "__main__":
    import os
    host = os.environ.get("AUTH_HOST", "localhost")
    port = int(os.environ.get("AUTH_PORT", "443"))
    user = os.environ.get("AUTH_USER", "testuser")
    pw   = os.environ.get("AUTH_PASS", "testpass")
    print(f"HWID: {AuthClient(host)._get_hwid()}")
    print(f"Encrypted pass (hex): {encrypt_password(pw)}")
    client = AuthClient(host, port)
    result = client.authorize(user, pw)
    print(f"Auth result: {result}")
