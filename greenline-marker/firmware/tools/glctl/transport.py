"""Transports: a serial port (the unit in its cradle; needs pyserial) and the
host simulator build of the firmware (build/host/glsim; needs nothing)."""
import json
import os
import struct
import subprocess

from .proto import ProtocolError

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SIM = os.path.normpath(os.path.join(HERE, "..", "..", "build", "host", "glsim"))


class SerialTransport:
    """A CDC-ACM port.  pyserial is imported here and only here."""

    def __init__(self, port, timeout=1.0):
        try:
            import serial  # noqa: PLC0415  (optional dependency)
        except ImportError:
            raise ProtocolError(
                "the serial transport needs the 'pyserial' package, which is not installed "
                "(python3 -m pip install pyserial).  Everything else in glctl works without it: "
                "the simulator transport (--sim), log decoding and the replay.")
        try:
            self.port = serial.Serial(port, 115200, timeout=0.05)
        except Exception as exc:  # serial.SerialException and OS errors
            raise ProtocolError("cannot open %s: %s" % (port, exc))
        self.timeout = timeout

    def write(self, data):
        self.port.write(data)

    def read(self, wait_s):
        self.port.timeout = wait_s
        return self.port.read(4096)

    def close(self):
        self.port.close()


class SimTransport:
    """The firmware's host simulator as a child process (tools/glsim_host.c)."""

    def __init__(self, path=None):
        path = path or DEFAULT_SIM
        if not os.path.exists(path):
            raise ProtocolError("the simulator build %s does not exist: run `make glsim` in firmware/" % path)
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.pending = b""

    def _frame(self, kind, data):
        self.proc.stdin.write(kind + struct.pack("<H", len(data)) + data)
        self.proc.stdin.flush()
        hdr = self.proc.stdout.read(3)
        if len(hdr) != 3:
            raise ProtocolError("the simulator has ended")
        n = struct.unpack_from("<H", hdr, 1)[0]
        body = self.proc.stdout.read(n) if n else b""
        return hdr[0:1], body

    def write(self, data):
        for i in range(0, len(data), 60000):
            kind, body = self._frame(b"U", data[i:i + 60000])
            self.pending += body

    def read(self, wait_s):
        if not self.pending:
            kind, body = self._frame(b"T", struct.pack("<I", max(1, int(wait_s * 1000))))
            self.pending += body
        out, self.pending = self.pending, b""
        return out

    def world(self, command):
        """A world command of the simulator (see tools/glsim_host.c); returns its JSON answer."""
        kind, body = self._frame(b"W", command.encode("ascii"))
        if kind != b"W":
            raise ProtocolError("the simulator did not answer the world command %r" % command)
        return json.loads(body.decode("ascii"))

    def close(self):
        try:
            self.world("quit")
        except Exception:
            pass
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
