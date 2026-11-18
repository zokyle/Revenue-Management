"""glctl - the PC side of the GreenLine GL-1 USB protocol (firmware/core/gl_proto.h).

    python3 tools/glctl --help

Python 3, standard library only.  The serial transport uses pyserial if it
is installed; the simulator transport (--sim) talks to the host build of the
firmware (build/host/glsim) and needs nothing.
"""
PROTO_VERSION = 3
