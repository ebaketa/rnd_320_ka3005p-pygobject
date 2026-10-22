#!/usr/bin/env python3

# *****************************************************************************
# Program:      KORAD DC POWER SUPPLY CONTROL
# Author:       Elvis Baketa
# Device:       RND 320-KA3005P
# Version:      0.4
# Requirements: Python3, PyGObject, pyserial
# *****************************************************************************

import os
import queue
import threading
import time
import traceback
from collections import namedtuple

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib

import serial

import korad

GLADE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rnd_320_ka3005p-pygobject.glade")

# pause between two display updates in seconds
UPDATE_INTERVAL = 0.5

# how long a message replaces the connection status in seconds
MESSAGE_TIMEOUT = 3

# number of memory slots of the device
MEMORY_SLOTS = 5

# active buttons are green, the value being entered is orange
CSS = b"""
button.active {
    background-image: none;
    background-color: #2e7d32;
    color: #ffffff;
}
label.editing {
    color: #e65100;
}
"""

# keyboard digits and keypad digits
DIGIT_KEYS = {}
for n in range(10):
    DIGIT_KEYS[getattr(Gdk, f"KEY_{n}")] = n
    DIGIT_KEYS[getattr(Gdk, f"KEY_KP_{n}")] = n

# how a voltage or current is entered: digits fill the value from the right,
# e.g. 1,2,3,4 gives 12.34V; the value is sent after the last digit or Enter
EntrySetting = namedtuple('EntrySetting', ['label', 'button', 'digits', 'scale', 'fmt', 'unit', 'maximum'])
ENTRY_SETTINGS = {
    'voltage': EntrySetting("lblDisplayVoltage", "btnSetVoltage", 4, 100, "{:05.2f}", "V", korad.MAX_VOLTAGE),
    'current': EntrySetting("lblDisplayCurrent", "btnSetCurrent", 4, 1000, "{:05.3f}", "A", korad.MAX_CURRENT),
}

# values read from the device in one update, commands_done is the number of
# commands that were executed before the reading started
Reading = namedtuple('Reading', ['state', 'set_voltage', 'set_current', 'output_voltage', 'output_current', 'commands_done'])


# background thread that owns the device: it runs queued commands and reads
# the device periodically, results are passed to the GUI thread with GLib.idle_add
class DeviceWorker(threading.Thread):
    # marks the end of the command queue
    STOP = object()

    def __init__(self, psu, on_reading, on_connection_lost):
        super().__init__(daemon=True)
        self.psu = psu
        self.on_reading = on_reading
        self.on_connection_lost = on_connection_lost
        self.commands = queue.Queue()
        self.commands_submitted = 0
        self.commands_done = 0
        self.running = True

    # queue a function that is called with the device as argument
    def submit(self, command):
        self.commands_submitted += 1
        self.commands.put(command)

    # read the device as soon as possible
    def request_update(self):
        self.submit(lambda psu: None)

    # a reading is outdated if a command was submitted after it started
    def is_outdated(self, reading):
        return reading.commands_done < self.commands_submitted

    # finish queued commands and stop the thread
    def stop(self):
        self.running = False
        self.commands.put(self.STOP)

    def run(self):
        next_update = 0
        while True:
            try:
                command = self.commands.get(timeout=max(0, next_update - time.monotonic()))
            except queue.Empty:
                command = None
            if command is self.STOP:
                return
            try:
                if command is not None:
                    try:
                        command(self.psu)
                    finally:
                        self.commands_done += 1
                # no need to read the device while stopping
                if self.running:
                    GLib.idle_add(self.on_reading, self.read())
            except korad.ConnectionLostError as error:
                GLib.idle_add(self.on_connection_lost, error)
                return
            except Exception:
                traceback.print_exc()
            next_update = time.monotonic() + UPDATE_INTERVAL

    def read(self):
        commands_done = self.commands_done
        state = self.psu.get_state()
        set_voltage = self.psu.get_set_voltage()
        set_current = self.psu.get_set_current()
        if state is not None and state.output:
            output_voltage = self.psu.get_output_voltage()
            output_current = self.psu.get_output_current()
        else:
            output_voltage = None
            output_current = None
        return Reading(state, set_voltage, set_current, output_voltage, output_current, commands_done)


class MainWindow:
    def __init__(self):
        self.output_on = False
        self.ovp_on = False
        self.ocp_on = False
        # 'voltage' or 'current' while the user enters a value, otherwise None
        self.entry_mode = None
        self.entry_digits = ''
        # waiting for the memory slot after the M key
        self.memory_select = False
        self.last_reading = None
        self.controls_enabled = False
        self.connection_message = ''
        self.message_timer = None
        self.worker = None

        # initialize communication port
        self.psu = None
        port_name = korad.find_port()
        if port_name is not None:
            try:
                self.psu = korad.KoradPSU(port_name)
            except serial.SerialException as error:
                print(f"Cannot open communication port {port_name}: {error}")

        # application window
        self.builder = Gtk.Builder()
        self.builder.add_from_file(GLADE_FILE)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.window = self.builder.get_object("mainWindow")
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_title("KORAD DC POWER SUPPLY CONTROL")
        self.window.connect("key-press-event", self.on_key_press_event)
        self.window.connect("destroy", Gtk.main_quit)
        self.window.connect("delete-event", self.on_delete)

        self.labels = {}
        for label_id in ("lblDisplayVoltage", "lblDisplayCurrent", "lblUserSetVoltage", "lblUserSetCurrent", "lblSerialPortStatus"):
            self.labels[label_id] = self.builder.get_object(label_id)

        self.btn_output = self.builder.get_object("btnOutputOnOff")
        self.btn_ovp = self.builder.get_object("btnOVP")
        self.btn_ocp = self.builder.get_object("btnOCP")

        # button id, handler and extra handler arguments
        buttons = [(f"btnN{digit}", self.on_digit_clicked, digit) for digit in range(10)]
        buttons += [(f"btnM{slot}", self.on_memory_clicked, slot) for slot in range(1, MEMORY_SLOTS + 1)]
        buttons += [
            ("btnSetVoltage", self.on_set_voltage_clicked),
            ("btnSetCurrent", self.on_set_current_clicked),
            ("btnOVP", self.on_ovp_clicked),
            ("btnOCP", self.on_ocp_clicked),
            ("btnOutputOnOff", self.on_output_clicked),
        ]
        # buttons that are usable only while the device is connected
        self.controls = []
        for button_id, handler, *args in buttons:
            button = self.builder.get_object(button_id)
            button.connect("clicked", handler, *args)
            self.controls.append(button)

        # keyboard shortcuts, digits are handled separately
        self.key_actions = {
            Gdk.KEY_o: lambda: self.on_output_clicked(None),
            Gdk.KEY_v: lambda: self.on_set_voltage_clicked(None),
            Gdk.KEY_a: lambda: self.on_set_current_clicked(None),
            Gdk.KEY_m: self.start_memory_select,
            Gdk.KEY_u: lambda: self.worker.request_update(),
            Gdk.KEY_Return: self.confirm_entry,
            Gdk.KEY_KP_Enter: self.confirm_entry,
            Gdk.KEY_Escape: self.cancel_entry,
            Gdk.KEY_BackSpace: self.delete_digit,
        }

        self.set_connected_state(False, 'The device is not connected or not turned on!')
        self.init_device()

    # check if communication with the device is possible
    def is_connected(self):
        return self.controls_enabled

    # enable or disable controls and show connection status
    def set_connected_state(self, connected, message):
        self.controls_enabled = connected
        for control in self.controls:
            control.set_sensitive(connected)
        self.connection_message = message
        self.restore_status()

    # show a message in the status line for a few seconds
    def show_message(self, message, timeout=MESSAGE_TIMEOUT):
        if self.message_timer is not None:
            GLib.source_remove(self.message_timer)
        self.labels["lblSerialPortStatus"].set_text(message)
        self.message_timer = GLib.timeout_add_seconds(timeout, self.restore_status)

    # show the connection status again
    def restore_status(self):
        if self.message_timer is not None:
            GLib.source_remove(self.message_timer)
            self.message_timer = None
        self.labels["lblSerialPortStatus"].set_text(self.connection_message)
        return False

    # add or remove a CSS class of a widget
    def set_style(self, widget, style_class, enabled):
        if enabled:
            widget.get_style_context().add_class(style_class)
        else:
            widget.get_style_context().remove_class(style_class)

    # show output, OVP and OCP state on their buttons
    def update_button_states(self):
        self.set_style(self.btn_output, "active", self.output_on)
        self.set_style(self.btn_ovp, "active", self.ovp_on)
        self.set_style(self.btn_ocp, "active", self.ocp_on)

    # disable controls after a communication error, the port is already closed
    def connection_lost(self, error):
        if not self.controls_enabled:
            return
        print(f"Communication error: {error}")
        self.set_connected_state(False, 'Connection to the device lost!')
        self.cancel_entry()
        self.memory_select = False
        self.last_reading = None
        self.output_on = False
        self.ovp_on = False
        self.ocp_on = False
        self.update_button_states()
        # do not leave stale values on the display
        self.labels["lblDisplayVoltage"].set_text("--V")
        self.labels["lblDisplayCurrent"].set_text("--A")
        self.labels["lblUserSetVoltage"].set_text("VSET: --V")
        self.labels["lblUserSetCurrent"].set_text("ISET: --A")

    # identify the device, enable controls and start periodic updates
    def init_device(self):
        if self.psu is None:
            return
        try:
            device_id = self.psu.identify()
        except korad.ConnectionLostError as error:
            print(f"Communication error: {error}")
            return
        self.set_connected_state(True, f"{device_id or 'Device'} connected via communication port: {self.psu.name}")
        self.worker = DeviceWorker(self.psu, self.update_display, self.connection_lost)
        self.worker.start()

    # queue a command for the device
    def send_command(self, command):
        if self.is_connected():
            self.worker.submit(command)

    def on_key_press_event(self, widget, event):
        if not self.is_connected():
            return False
        # leave shortcuts like Ctrl+Q or Alt+F4 to the window manager
        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        digit = DIGIT_KEYS.get(event.keyval)
        # M followed by 1-5 recalls a memory, any other key cancels it
        if self.memory_select:
            self.memory_select = False
            self.restore_status()
            if digit is not None and 1 <= digit <= MEMORY_SLOTS:
                self.on_memory_clicked(None, digit)
            return True
        if digit is not None:
            self.on_digit_clicked(None, digit)
            return True
        action = self.key_actions.get(event.keyval)
        if action is None:
            return False
        action()
        return True

    # format a value for the display, or a placeholder if it is not available
    def format_value(self, value, fmt, unit):
        if value is None:
            return "--" + unit
        return fmt.format(value) + unit

    # show values read by the worker, called in the GUI thread
    def update_display(self, reading):
        if not self.is_connected():
            return
        # a newer reading follows, this one could undo the last button press
        if self.worker.is_outdated(reading):
            return
        self.last_reading = reading
        # output, OVP and OCP can also be changed on the front panel
        if reading.state is not None:
            self.output_on = reading.state.output
            self.ovp_on = reading.state.ovp
            self.ocp_on = reading.state.ocp
        self.update_button_states()
        if self.output_on:
            display_voltage = reading.output_voltage
            display_current = reading.output_current
        else:
            display_voltage = reading.set_voltage
            display_current = reading.set_current
        # keep the value the user is entering
        if self.entry_mode != 'voltage':
            self.labels["lblDisplayVoltage"].set_text(self.format_value(display_voltage, "{:05.2f}", "V"))
        if self.entry_mode != 'current':
            self.labels["lblDisplayCurrent"].set_text(self.format_value(display_current, "{:05.3f}", "A"))
        self.labels["lblUserSetVoltage"].set_text("VSET: " + self.format_value(reading.set_voltage, "{:05.2f}", "V"))
        self.labels["lblUserSetCurrent"].set_text("ISET: " + self.format_value(reading.set_current, "{:05.3f}", "A"))

    def on_delete(self, widget, data=None):
        if self.worker is not None:
            # disable output before closing, queued after any pending commands
            self.send_command(lambda psu: psu.set_output(False))
            self.worker.stop()
            self.worker.join(timeout=3)
        if self.psu is not None:
            self.psu.close()

    # start entering a voltage or current, the same button again cancels it
    def start_entry(self, mode):
        if not self.is_connected():
            return
        if self.entry_mode == mode:
            self.cancel_entry()
            return
        self.cancel_entry()
        setting = ENTRY_SETTINGS[mode]
        self.entry_mode = mode
        self.entry_digits = ''
        self.set_style(self.labels[setting.label], "editing", True)
        self.set_style(self.builder.get_object(setting.button), "active", True)
        self.show_entry()

    # value of the digits entered so far
    def entry_value(self):
        return int(self.entry_digits or '0') / ENTRY_SETTINGS[self.entry_mode].scale

    def show_entry(self):
        setting = ENTRY_SETTINGS[self.entry_mode]
        self.labels[setting.label].set_text(setting.fmt.format(self.entry_value()) + setting.unit)

    # stop entering a value, the display shows the device values again
    def cancel_entry(self):
        if self.entry_mode is None:
            return
        setting = ENTRY_SETTINGS[self.entry_mode]
        self.set_style(self.labels[setting.label], "editing", False)
        self.set_style(self.builder.get_object(setting.button), "active", False)
        self.entry_mode = None
        self.entry_digits = ''
        if self.last_reading is not None:
            self.update_display(self.last_reading)

    # send the entered value to the device if it is within the device limits
    def confirm_entry(self):
        if self.entry_mode is None or self.entry_digits == '':
            self.cancel_entry()
            return
        setting = ENTRY_SETTINGS[self.entry_mode]
        value = self.entry_value()
        mode = self.entry_mode
        self.cancel_entry()
        if value > setting.maximum:
            self.show_message(f"Value out of range, maximum is {setting.fmt.format(setting.maximum)}{setting.unit}")
            return
        if mode == 'voltage':
            self.send_command(lambda psu: psu.set_voltage(value))
        else:
            self.send_command(lambda psu: psu.set_current(value))
        # show the new value until the device confirms it
        self.labels[setting.label].set_text(setting.fmt.format(value) + setting.unit)

    def delete_digit(self):
        if self.entry_mode is None:
            return
        self.entry_digits = self.entry_digits[:-1]
        self.show_entry()

    # wait for the memory slot number on the keyboard
    def start_memory_select(self):
        self.memory_select = True
        self.show_message(f"Recall memory: press 1-{MEMORY_SLOTS}, any other key cancels")

    def on_set_voltage_clicked(self, button):
        self.start_entry('voltage')

    def on_set_current_clicked(self, button):
        self.start_entry('current')

    def on_digit_clicked(self, button, digit):
        if not self.is_connected() or self.entry_mode is None:
            return
        self.entry_digits += str(digit)
        self.show_entry()
        if len(self.entry_digits) == ENTRY_SETTINGS[self.entry_mode].digits:
            self.confirm_entry()

    # recall settings from memory slot, output is disabled first
    def on_memory_clicked(self, button, slot):
        self.cancel_entry()
        self.output_on = False
        self.update_button_states()
        def recall(psu):
            psu.set_output(False)
            psu.recall(slot)
        self.send_command(recall)
        self.show_message(f"Memory M{slot} recalled, output disabled")

    def on_output_clicked(self, button):
        self.output_on = not self.output_on
        self.update_button_states()
        enabled = self.output_on
        self.send_command(lambda psu: psu.set_output(enabled))

    def on_ovp_clicked(self, button):
        self.ovp_on = not self.ovp_on
        self.update_button_states()
        enabled = self.ovp_on
        self.send_command(lambda psu: psu.set_ovp(enabled))

    def on_ocp_clicked(self, button):
        self.ocp_on = not self.ocp_on
        self.update_button_states()
        enabled = self.ocp_on
        self.send_command(lambda psu: psu.set_ocp(enabled))


if __name__ == '__main__':
    main = MainWindow()
    main.window.show()
    Gtk.main()
