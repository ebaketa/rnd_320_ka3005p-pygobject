import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import serial

import korad


# serial port that answers queries like a KA3005P
class FakeSerial:
    def __init__(self, responses):
        self.responses = responses
        self.written = []
        self.buffer = b''
        self.is_open = True
        self.name = '/dev/ttyFAKE'
        self.fail = False

    @property
    def in_waiting(self):
        if self.fail:
            raise serial.SerialException("device disconnected")
        return len(self.buffer)

    def write(self, data):
        if self.fail:
            raise serial.SerialException("device disconnected")
        command = data.decode()
        self.written.append(command)
        self.buffer += self.responses.get(command, b'')

    def read(self, size):
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def reset_input_buffer(self):
        self.buffer = b''

    def close(self):
        self.is_open = False


class KoradPSUTest(unittest.TestCase):
    def make_psu(self, responses=None):
        self.port = FakeSerial(responses or {})
        with mock.patch.object(korad.serial, 'Serial', return_value=self.port):
            return korad.KoradPSU('/dev/ttyFAKE')

    def setUp(self):
        # commands do not need to wait for a real device
        patcher = mock.patch.object(korad, 'COMMAND_DELAY', 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_identify(self):
        psu = self.make_psu({'*IDN?': b'RND 320-KA3005P V2.0'})
        self.assertEqual(psu.identify(), 'RND 320-KA3005P V2.0')

    def test_values(self):
        psu = self.make_psu({'VSET1?': b'12.34', 'VOUT1?': b'12.33', 'IOUT1?': b'0.123'})
        self.assertEqual(psu.get_set_voltage(), 12.34)
        self.assertEqual(psu.get_output_voltage(), 12.33)
        self.assertEqual(psu.get_output_current(), 0.123)

    def test_extra_digit_in_current_is_ignored(self):
        psu = self.make_psu({'ISET1?': b'0.1002'})
        self.assertEqual(psu.get_set_current(), 0.1)

    def test_invalid_or_missing_response(self):
        psu = self.make_psu({'VSET1?': b'garbage'})
        with mock.patch('builtins.print'):
            self.assertIsNone(psu.get_set_voltage())
            self.assertIsNone(psu.get_set_current())

    def test_state(self):
        # bits verified on RND 320-KA3005P V2.0
        for status, expected in (
                (0x01, korad.PSUState(output=False, ovp=False, ocp=False)),
                (0x41, korad.PSUState(output=True, ovp=False, ocp=False)),
                (0x81, korad.PSUState(output=False, ovp=True, ocp=False)),
                (0x21, korad.PSUState(output=False, ovp=False, ocp=True)),
                # a status byte that looks like whitespace must not be stripped
                (0x20, korad.PSUState(output=False, ovp=False, ocp=True)),
        ):
            psu = self.make_psu({'STATUS?': bytes([status])})
            self.assertEqual(psu.get_state(), expected, hex(status))

    def test_state_without_response(self):
        psu = self.make_psu()
        self.assertIsNone(psu.get_state())

    def test_commands(self):
        psu = self.make_psu()
        psu.set_voltage(5)
        psu.set_current(0.1)
        psu.set_output(True)
        psu.set_ovp(False)
        psu.set_ocp(True)
        psu.recall(3)
        self.assertEqual(self.port.written, ['VSET1:05.00', 'ISET1:0.100', 'OUT1', 'OVP0', 'OCP1', 'RCL3'])

    def test_limits(self):
        psu = self.make_psu()
        psu.set_voltage(korad.MAX_VOLTAGE)
        psu.set_current(korad.MAX_CURRENT)
        for setter, value in ((psu.set_voltage, 30.01), (psu.set_voltage, -1), (psu.set_current, 5.001)):
            with self.assertRaises(ValueError):
                setter(value)
        self.assertEqual(self.port.written, ['VSET1:30.00', 'ISET1:5.000'])

    def test_connection_lost(self):
        psu = self.make_psu()
        self.port.fail = True
        with self.assertRaises(korad.ConnectionLostError):
            psu.set_output(True)
        self.assertFalse(psu.is_open)
        # later calls fail immediately without touching the port
        with self.assertRaises(korad.ConnectionLostError):
            psu.get_state()

    def test_find_port(self):
        ports = [
            mock.Mock(vid=None, pid=None, device='/dev/ttyS0'),
            mock.Mock(vid=1027, pid=24577, device='/dev/ttyUSB0'),
            mock.Mock(vid=korad.DEVICE_VID, pid=korad.DEVICE_PID, device='/dev/ttyACM0'),
        ]
        with mock.patch.object(korad.serial.tools.list_ports, 'comports', return_value=ports):
            self.assertEqual(korad.find_port(), '/dev/ttyACM0')
        with mock.patch.object(korad.serial.tools.list_ports, 'comports', return_value=ports[:2]):
            self.assertIsNone(korad.find_port())


if __name__ == '__main__':
    unittest.main()
