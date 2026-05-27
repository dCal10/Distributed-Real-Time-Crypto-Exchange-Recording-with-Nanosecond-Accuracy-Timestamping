"""Spike: probe whether the `websockets` library exposes the raw socket enough
to call recvmsg() with SO_TIMESTAMPING and pull NIC hardware timestamps.

Run on the EC2 box AFTER P1 deploy verification, while the verify capture is
recording. The outcome decides whether P2's path (a) (hijack the websockets
socket) is viable or whether (b) (hand-roll WS on a raw socket with asyncio
add_reader) is required. See infra/README.md "Q7 spike" for context.

Usage:
    python tests/spike_so_timestamping.py

This is a throwaway diagnostic. Delete once P2 lands.
"""

from __future__ import annotations

import asyncio
import socket
import struct

import websockets

SO_TIMESTAMPING = 37
SCM_TIMESTAMPING = 37
SOF_TIMESTAMPING_RX_HARDWARE = 1 << 2
SOF_TIMESTAMPING_RX_SOFTWARE = 1 << 3
SOF_TIMESTAMPING_RAW_HARDWARE = 1 << 6


async def main() -> None:
    uri = "wss://data-stream.binance.vision/ws/btcusdt@depth"
    async with websockets.connect(uri) as ws:
        transport = ws.transport
        sock = transport.get_extra_info("socket")
        if sock is None:
            print("FAIL  websockets transport did not expose underlying socket")
            print("      path (a) blocked at step 1; P2 must use (b)")
            return
        print(f"OK    socket family={sock.family.name} fd={sock.fileno()}")

        flags = (
            SOF_TIMESTAMPING_RX_HARDWARE
            | SOF_TIMESTAMPING_RX_SOFTWARE
            | SOF_TIMESTAMPING_RAW_HARDWARE
        )
        try:
            sock.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING, flags)
            print(f"OK    setsockopt SO_TIMESTAMPING flags=0x{flags:x}")
        except OSError as e:
            print(f"FAIL  setsockopt SO_TIMESTAMPING: {e}")
            print("      kernel/NIC does not support hardware timestamping")
            return

        for _ in range(3):
            await ws.recv()
        print("OK    3 WS frames flowed after SO_TIMESTAMPING set (no library breakage)")

        sock.setblocking(False)
        try:
            msg, ancdata, _flags_out, _addr = sock.recvmsg(4096, socket.CMSG_SPACE(64))
            print(f"OK    recvmsg msg_len={len(msg)} ancdata_count={len(ancdata)}")
            for level, ctype, data in ancdata:
                print(f"      cmsg level={level} type={ctype} data_len={len(data)}")
                if level == socket.SOL_SOCKET and ctype == SCM_TIMESTAMPING and len(data) >= 48:
                    sw_sec, sw_nsec = struct.unpack("ll", data[0:16])
                    hw_sec, hw_nsec = struct.unpack("ll", data[32:48])
                    print(f"      SCM_TIMESTAMPING sw={sw_sec}.{sw_nsec:09d} hw={hw_sec}.{hw_nsec:09d}")
                    if hw_sec == 0 and hw_nsec == 0:
                        print("      hw stamp is zero; NIC HW timestamping NOT active on this socket")
                        print("      path (a) cannot deliver per-packet HW; check ENA + PHC + driver")
                    else:
                        print("      hw stamp present; path (a) is viable for P2")
            if not ancdata:
                print("INFO  ancdata empty; library consumed the cmsg before we got it")
                print("      path (a) is likely not viable; consider (b)")
        except BlockingIOError:
            print("INFO  recvmsg would block; websockets library is buffering ahead of socket")
            print("      path (a) requires hooking above the socket; consider (b)")
        except OSError as e:
            print(f"FAIL  recvmsg: {e}")


if __name__ == "__main__":
    asyncio.run(main())
