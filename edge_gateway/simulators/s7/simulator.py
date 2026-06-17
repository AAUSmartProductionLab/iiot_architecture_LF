"""
Minimal Siemens S7 simulator (snap7 server).

Serves a DB (default DB1) whose first 4 bytes hold a fluctuating temperature as
an S7 REAL (big-endian float32), so an S7 client can read it like a real PLC.
"""

import logging
import math
import os
import struct
import time

import snap7
from snap7.server import Server
from snap7.type import SrvArea

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("s7-sim")

DB_NUMBER = int(os.getenv("DB_NUMBER", "1"))
DB_SIZE = int(os.getenv("DB_SIZE", "4"))
BASE_TEMP = float(os.getenv("BASE_TEMP", "20"))
AMPLITUDE = float(os.getenv("AMPLITUDE", "5"))
PERIOD = float(os.getenv("PERIOD", "30"))


def main() -> None:
    # Must be a bytearray: the server keeps this reference, so in-place updates
    # are served to clients (a ctypes array would be copied instead).
    data = bytearray(DB_SIZE)
    server = Server()
    server.register_area(SrvArea.DB, DB_NUMBER, data)
    server.start()  # binds ISO-TSAP on :102
    log.info("S7 server started — DB%d (%d bytes) on :102", DB_NUMBER, DB_SIZE)

    t0 = time.time()
    while True:
        temp = BASE_TEMP + AMPLITUDE * math.sin((time.time() - t0) * 2 * math.pi / PERIOD)
        struct.pack_into(">f", data, 0, temp)  # S7 REAL = big-endian float32
        log.info("sim DB%d temperature = %.2f", DB_NUMBER, temp)
        time.sleep(2)


if __name__ == "__main__":
    main()
