"""RawWebSocketClient: a raw-socket WSS client that exposes NIC RX timestamps.

The high-level `websockets` library buffers ahead of the kernel socket, so
external `recvmsg` sees no data and SO_TIMESTAMPING ancillary data is
unreachable (Q7 spike). This client owns the socket end to end:

    raw TCP socket (SO_TIMESTAMPING enabled)
        -> recvmsg() + SCM_TIMESTAMPING cmsg parse  (per-TCP-chunk t_ns)
        -> ssl.MemoryBIO  (TLS termination, handshake driven by hand)
        -> wsproto  (WS handshake + framing: ping/pong/close/fragmentation)
        -> yield (payload, chunk_timestamps) to the collector

The async surface is `connect()` then `async for (payload, chunks) in
messages()`. Blocking setup (TCP connect, TLS handshake, WS handshake) runs
in a thread executor; the steady-state recv loop is a single coroutine using
the asyncio add_reader pattern on the raw fd.

Per-message chunk attribution model: every TCP chunk read since the previous
complete WS message is attributed to the next complete message. A chunk that
straddles two WS messages is counted toward the later one. This matches the
proposal section 6 reassembly-profile model and ADR-0012. Messages assembled
from bytes received during the handshake (before the data-phase recv loop)
carry an empty chunk list; NICTimestampSource emits the 0 "not available"
sentinel for those, which is the documented contract.

Linux-only for real timestamps. On macOS dev the SO_TIMESTAMPING setsockopt
fails; the client logs nothing and proceeds with timestamps reported as 0, so
the WS/TLS/Parquet pipeline can still be exercised locally. Real HW timestamp
validation happens on the Tokyo Linux box (Step 6). See ADR-0012.
"""

from __future__ import annotations

import asyncio
import socket
import ssl
import struct
from collections.abc import AsyncIterator

from wsproto import ConnectionType, WSConnection
from wsproto.events import (
    AcceptConnection,
    BytesMessage,
    CloseConnection,
    Ping,
    RejectConnection,
    Request,
    TextMessage,
)

_SO_TIMESTAMPING = 37
_SCM_TIMESTAMPING = 37
_SOF_TIMESTAMPING_RX_HARDWARE = 1 << 2
_SOF_TIMESTAMPING_RX_SOFTWARE = 1 << 3
_SOF_TIMESTAMPING_RAW_HARDWARE = 1 << 6
_TS_FLAGS = (
    _SOF_TIMESTAMPING_RX_HARDWARE
    | _SOF_TIMESTAMPING_RAW_HARDWARE
    | _SOF_TIMESTAMPING_RX_SOFTWARE
)

_BUFSIZE = 65536
_CMSG_BUF = 64

_CLOSED = object()


def _extract_hw_ns(ancdata: list) -> int:
    """Pull the NIC RX timestamp from recvmsg ancillary data.

    SCM_TIMESTAMPING delivers a `struct scm_timestamping` = 3 contiguous
    `struct timespec` (each two 64-bit fields on 64-bit Linux): index 0 is
    the software stamp, index 1 the deprecated/legacy slot, index 2 the raw
    hardware stamp. Prefer hardware, fall back to software, and return the
    0 sentinel if neither is present (non-Linux, HW not delivered, or an
    unexpected cmsg layout).
    """
    for level, cmsg_type, cmsg_data in ancdata:
        if level == socket.SOL_SOCKET and cmsg_type == _SCM_TIMESTAMPING:
            if len(cmsg_data) >= 48:
                sw_s, sw_ns, _d_s, _d_ns, hw_s, hw_ns = struct.unpack(
                    "qqqqqq", cmsg_data[:48]
                )
                hw = hw_s * 1_000_000_000 + hw_ns
                if hw:
                    return hw
                return sw_s * 1_000_000_000 + sw_ns
    return 0


class RawWebSocketClient:
    def __init__(
        self,
        host: str,
        path: str,
        port: int = 443,
        server_hostname: str | None = None,
    ) -> None:
        self._host = host
        self._path = path
        self._port = port
        self._server_hostname = server_hostname or host
        self._sock: socket.socket | None = None
        self._sslobj: ssl.SSLObject | None = None
        self._incoming: ssl.MemoryBIO | None = None
        self._outgoing: ssl.MemoryBIO | None = None
        self._ws: WSConnection | None = None
        self._hw_ts_enabled = False
        self._pending_chunks: list[tuple[int, int]] = []
        self._frag: list = []

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._blocking_connect)

    async def messages(self) -> AsyncIterator[tuple[object, tuple[tuple[int, int], ...]]]:
        assert self._sock is not None
        while True:
            # Drain whatever wsproto already buffered first: handshake
            # over-read, or several WS messages inside one TLS record. Doing
            # this before awaiting readable avoids stalling on a message that
            # is already in hand.
            for item in self._drain_events():
                if item is _CLOSED:
                    return
                yield item

            await self._wait_readable()
            try:
                raw, ancdata, _flags, _addr = self._sock.recvmsg(
                    _BUFSIZE, socket.CMSG_SPACE(_CMSG_BUF)
                )
            except BlockingIOError:
                continue
            if not raw:
                raise ConnectionError("peer closed the connection")

            t_ns = _extract_hw_ns(ancdata)
            self._pending_chunks.append((t_ns, len(raw)))

            cleartext = self._tls_feed(raw)
            if cleartext:
                self._ws.receive_data(cleartext)

    async def close(self) -> None:
        # Best-effort close handshake; the socket teardown is what matters.
        try:
            if self._ws is not None and self._sock is not None:
                self._tls_send(self._ws.send(CloseConnection(code=1000)))
        except (OSError, ssl.SSLError):
            pass
        finally:
            if self._sock is not None:
                self._sock.close()

    async def send(self, payload: str | bytes) -> None:
        """Send a WS message (TextMessage if str, BytesMessage if bytes).

        Used for post-handshake subscription frames: Coinbase sends one
        subscribe per channel, OKX one combined subscribe. Call after
        connect() and before the messages() loop. The socket is already
        non-blocking at that point (connect() ends with setblocking(False)).

        _flush_outgoing's sendall can in principle raise BlockingIOError if
        the kernel send buffer is full. For a few-hundred-byte subscribe
        frame written once on a freshly opened connection (send buffer
        empty) that does not occur in practice, so the writable-callback
        buffer deferred per ADR-0012 is intentionally not added here. This
        client only ever sends low-rate control and subscribe frames;
        high-rate sending is out of scope.
        """
        assert self._ws is not None and self._sock is not None
        if isinstance(payload, str):
            event: TextMessage | BytesMessage = TextMessage(data=payload)
        else:
            event = BytesMessage(data=payload)
        self._tls_send(self._ws.send(event))

    # --- blocking setup (runs in executor) ---------------------------------

    def _blocking_connect(self) -> None:
        self._sock = socket.create_connection((self._host, self._port))
        try:
            self._sock.setsockopt(socket.SOL_SOCKET, _SO_TIMESTAMPING, _TS_FLAGS)
            self._hw_ts_enabled = True
        except OSError:
            # macOS / unsupported kernel: proceed without HW timestamps so the
            # WS/TLS/Parquet pipeline is still exercisable in local dev. Real
            # timestamps are validated on the Tokyo Linux box.
            self._hw_ts_enabled = False

        ctx = ssl.create_default_context()
        self._incoming = ssl.MemoryBIO()
        self._outgoing = ssl.MemoryBIO()
        self._sslobj = ctx.wrap_bio(
            self._incoming, self._outgoing, server_hostname=self._server_hostname
        )
        self._tls_handshake_blocking()

        self._ws = WSConnection(ConnectionType.CLIENT)
        self._tls_send(
            self._ws.send(Request(host=self._server_hostname, target=self._path))
        )
        self._ws_handshake_blocking()

        self._sock.setblocking(False)

    def _tls_handshake_blocking(self) -> None:
        while True:
            try:
                self._sslobj.do_handshake()
                break
            except ssl.SSLWantReadError:
                self._flush_outgoing()
                data = self._sock.recv(_BUFSIZE)
                if not data:
                    raise ConnectionError("peer closed during TLS handshake")
                self._incoming.write(data)
            except ssl.SSLWantWriteError:
                self._flush_outgoing()
        self._flush_outgoing()

    def _ws_handshake_blocking(self) -> None:
        while True:
            data = self._sock.recv(_BUFSIZE)
            if not data:
                raise ConnectionError("peer closed during WS handshake")
            cleartext = self._tls_feed(data)
            if not cleartext:
                continue
            self._ws.receive_data(cleartext)
            for event in self._ws.events():
                if isinstance(event, AcceptConnection):
                    return
                if isinstance(event, RejectConnection):
                    raise ConnectionError(
                        f"WS handshake rejected: status={event.status_code}"
                    )

    # --- TLS BIO shuttle ---------------------------------------------------

    def _flush_outgoing(self) -> None:
        data = self._outgoing.read()
        if data:
            # sendall on a non-blocking socket can raise BlockingIOError if the
            # kernel send buffer is full. For the data phase this only carries
            # low-rate control frames (pong/close), so it is not handled here;
            # a writable-callback buffer is deferred per ADR-0012 scope.
            self._sock.sendall(data)

    def _tls_feed(self, raw: bytes) -> bytes:
        self._incoming.write(raw)
        out: list[bytes] = []
        while True:
            try:
                chunk = self._sslobj.read(_BUFSIZE)
            except ssl.SSLWantReadError:
                break
            if not chunk:
                break
            out.append(chunk)
        return b"".join(out)

    def _tls_send(self, plaintext: bytes) -> None:
        if not plaintext:
            return
        self._sslobj.write(plaintext)
        self._flush_outgoing()

    # --- WS event pump -----------------------------------------------------

    def _drain_events(self):
        # Every WS message decoded in this drain came from the bytes of the
        # TCP chunks accumulated since the last drain that produced messages.
        # Those messages physically arrived in the same NIC RX window, so they
        # all get the SAME chunk snapshot (shared immutable tuple; downstream
        # builds its own per-message packet_metadata from it). Clear the
        # accumulator once, at the end, and only if a message was produced --
        # that lets a partial frame's chunks carry forward until it completes.
        # See ADR-0012 / proposal section 6.
        chunks = tuple(self._pending_chunks)
        produced = False
        for event in self._ws.events():
            if isinstance(event, (TextMessage, BytesMessage)):
                self._frag.append(event.data)
                if event.message_finished:
                    if isinstance(event, TextMessage):
                        payload: object = "".join(self._frag)
                    else:
                        payload = b"".join(self._frag)
                    self._frag.clear()
                    produced = True
                    yield (payload, chunks)
            elif isinstance(event, Ping):
                self._tls_send(self._ws.send(event.response()))
            elif isinstance(event, CloseConnection):
                self._tls_send(self._ws.send(event.response()))
                yield _CLOSED
                return
        if produced:
            self._pending_chunks.clear()

    # --- asyncio readable wait --------------------------------------------

    async def _wait_readable(self) -> None:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        fd = self._sock.fileno()
        loop.add_reader(fd, self._set_readable, fut)
        try:
            await fut
        finally:
            loop.remove_reader(fd)

    @staticmethod
    def _set_readable(fut: asyncio.Future) -> None:
        if not fut.done():
            fut.set_result(None)
