"""Low-level transports for the NIC-hardware-timestamp collector path.

`raw_ws.RawWebSocketClient` owns the socket so it can call recvmsg() and read
SO_TIMESTAMPING ancillary data, which the high-level websockets library hides
by buffering ahead of the kernel socket (Q7 spike). See ADR-0012.
"""
