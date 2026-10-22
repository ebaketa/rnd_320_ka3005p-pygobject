# *****************************************************************************
# Module:       KORAD DC POWER SUPPLY DRIVER
# Author:       Elvis Baketa
# Device:       RND 320-KA3005P
# Requirements: Python3, pyserial
# *****************************************************************************

import re
from collections import namedtuple
import termios
import time

import serial
import serial.tools.list_ports

# USB identification of the power supply (VID=1046, PID=20497)
DEVICE_VID = 1046
DEVICE_PID = 20497

# delay after a command so the device can process it
COMMAND_DELAY = 0.15
# maximum time to wait for a response
RESPONSE_TIMEOUT = 0.5
# response is complete when no new bytes arrive for this long
RESPONSE_QUIET_TIME = 0.05

# output limits of the device
MAX_VOLTAGE = 30.00
MAX_CURRENT = 5.000

# STATUS? response bits (OVP and OCP verified on RND 320-KA3005P V2.0)
STATUS_CV_MODE = 0x01
STATUS_OCP_ON = 0x20
STATUS_OUTPUT_ON = 0x40
STATUS_OVP_ON = 0x80

PSUState = namedtuple('PSUState', ['output', 'ovp', 'ocp'])

# errors raised when the device is unplugged or the port fails
COMMUNICATION_ERRORS = (serial.SerialException, OSError, termios.error)


class ConnectionLostError(Exception):
    """Communication with the device failed; the port has been closed."""


# find the device among serial ports and return port name, or None if not found
def find_port():
    for serial_port in serial.tools.list_ports.comports():
        if serial_port.vid == DEVICE_VID and serial_port.pid == DEVICE_PID:
            return serial_port.device
    return None


class KoradPSU:
    # open the communication port, raises serial.SerialException on failure
    def __init__(self, port_name):
        self.port = serial.Serial(port_name, timeout=0.5)

    @property
    def name(self):
        return self.port.name

    @property
    def is_open(self):
        return self.port.is_open

    def close(self):
        try:
            self.port.close()
        except COMMUNICATION_ERRORS:
            pass

    # close the port and report the error to the caller
    def _lost(self, error):
        self.close()
        raise ConnectionLostError(error) from error

    def _check_open(self):
        if not self.port.is_open:
            raise ConnectionLostError("communication port is closed")

    # send a command that has no response
    def _write(self, cmd):
        self._check_open()
        try:
            self.port.write(cmd.encode('ascii'))
        except COMMUNICATION_ERRORS as error:
            self._lost(error)
        time.sleep(COMMAND_DELAY)

    # send a query and return the raw response
    def _query(self, cmd):
        self._check_open()
        response = bytearray()
        try:
            self.port.reset_input_buffer()
            self.port.write(cmd.encode('ascii'))
            deadline = time.monotonic() + RESPONSE_TIMEOUT
            last_byte_time = None
            # the device does not terminate responses, so read until the line goes quiet
            while time.monotonic() < deadline:
                waiting = self.port.in_waiting
                if waiting > 0:
                    response += self.port.read(waiting)
                    last_byte_time = time.monotonic()
                elif last_byte_time is not None and time.monotonic() - last_byte_time > RESPONSE_QUIET_TIME:
                    break
                else:
                    time.sleep(0.005)
        except COMMUNICATION_ERRORS as error:
            self._lost(error)
        return bytes(response)

    # send a query and return the response as text
    def _query_text(self, cmd):
        return self._query(cmd).decode('ascii', errors='ignore').strip()

    # send a query and return the response as a number, or None if it is not valid;
    # only the given number of decimals is used, some firmware appends an extra digit
    def _query_float(self, cmd, decimals):
        response = self._query_text(cmd)
        match = re.search(r'\d+\.\d{%d}' % decimals, response)
        if match is None:
            print(f"Unexpected response to {cmd}: {response!r}")
            return None
        return float(match.group())

    # device identification
    def identify(self):
        return self._query_text('*IDN?')

    # device status byte, or None if the device did not answer
    def status(self):
        response = self._query('STATUS?')
        if len(response) == 0:
            return None
        return response[0]

    # output, OVP and OCP state from one status query, or None if unknown
    def get_state(self):
        status = self.status()
        if status is None:
            return None
        return PSUState(
            output=bool(status & STATUS_OUTPUT_ON),
            ovp=bool(status & STATUS_OVP_ON),
            ocp=bool(status & STATUS_OCP_ON),
        )

    def get_set_voltage(self):
        return self._query_float('VSET1?', 2)

    def get_set_current(self):
        return self._query_float('ISET1?', 3)

    def get_output_voltage(self):
        return self._query_float('VOUT1?', 2)

    def get_output_current(self):
        return self._query_float('IOUT1?', 3)

    def set_voltage(self, voltage):
        if not 0 <= voltage <= MAX_VOLTAGE:
            raise ValueError(f"voltage {voltage} V is out of range 0-{MAX_VOLTAGE} V")
        self._write(f"VSET1:{voltage:05.2f}")

    def set_current(self, current):
        if not 0 <= current <= MAX_CURRENT:
            raise ValueError(f"current {current} A is out of range 0-{MAX_CURRENT} A")
        self._write(f"ISET1:{current:05.3f}")

    def set_output(self, enabled):
        self._write('OUT1' if enabled else 'OUT0')

    def set_ovp(self, enabled):
        self._write('OVP1' if enabled else 'OVP0')

    def set_ocp(self, enabled):
        self._write('OCP1' if enabled else 'OCP0')

    # recall settings from memory slot 1-5
    def recall(self, slot):
        self._write(f"RCL{slot}")
