"""Classic TTARCH table writer; encrypted script payloads come from ttarchext."""
import struct


def pack(entries):
    """Write the v3 plaintext index used by working local translation patches.

    entries maps flat .lenc names to bytes already encrypted with this game's
    v7+ Lua cipher. This avoids ttarchext's incomplete v9 writer and emits a
    sorted index with an explicit root directory. No assets are decrypted here.
    """
    if not entries:
        raise ValueError("No scripts to package")
    table = bytearray(struct.pack("<II", 1, 1) + b"." + struct.pack("<I", len(entries)))
    payload = bytearray()
    for name in sorted(entries, key=str.lower):
        if "/" in name or "\\" in name or not name.endswith(".lenc"):
            raise ValueError(f"Invalid patch entry: {name}")
        encoded = name.encode("ascii")
        data = entries[name]
        table += struct.pack("<I", len(encoded)) + encoded
        table += struct.pack("<III", 0, len(payload), len(data))
        payload += data
    return struct.pack("<7I", 3, 0, 2, 1, 0, len(payload), len(table)) + table + payload
