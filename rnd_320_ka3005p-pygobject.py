#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# *****************************************************************************
# Program:      KORAD DC POWER SUPPLY CONTROL
# Author:       Elvis Baketa
# Device:       RND 320-KA3005P
# Version:      0.3
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

# values read from the device in one update, commandsDone is the number of
# commands that were executed before the reading started
Reading = namedtuple('Reading', ['state', 'setVoltage', 'setCurrent', 'outputVoltage', 'outputCurrent', 'commandsDone'])

# background thread that owns the device: it runs queued commands and reads
# the device periodically, results are passed to the GUI thread with GLib.idle_add
class DeviceWorker(threading.Thread):
    # marks the end of the command queue
    STOP = object()

    def __init__(self, psu, onReading, onConnectionLost):
        super().__init__(daemon=True)
        self.psu = psu
        self.onReading = onReading
        self.onConnectionLost = onConnectionLost
        self.commands = queue.Queue()
        self.commandsSubmitted = 0
        self.commandsDone = 0
        self.running = True

    # queue a function that is called with the device as argument
    def submit(self, command):
        self.commandsSubmitted += 1
        self.commands.put(command)

    # read the device as soon as possible
    def requestUpdate(self):
        self.submit(lambda psu: None)

    # a reading is outdated if a command was submitted after it started
    def isOutdated(self, reading):
        return reading.commandsDone < self.commandsSubmitted

    # finish queued commands and stop the thread
    def stop(self):
        self.running = False
        self.commands.put(self.STOP)

    def run(self):
        nextUpdate = 0
        while(True):
            try:
                command = self.commands.get(timeout=max(0, nextUpdate - time.monotonic()))
            except queue.Empty:
                command = None
            if(command is self.STOP):
                return
            try:
                if(command is not None):
                    try:
                        command(self.psu)
                    finally:
                        self.commandsDone += 1
                # no need to read the device while stopping
                if(self.running):
                    GLib.idle_add(self.onReading, self.read())
            except korad.ConnectionLostError as error:
                GLib.idle_add(self.onConnectionLost, error)
                return
            except Exception:
                traceback.print_exc()
            nextUpdate = time.monotonic() + UPDATE_INTERVAL

    def read(self):
        commandsDone = self.commandsDone
        state = self.psu.get_state()
        setVoltage = self.psu.get_set_voltage()
        setCurrent = self.psu.get_set_current()
        if(state is not None and state.output):
            outputVoltage = self.psu.get_output_voltage()
            outputCurrent = self.psu.get_output_current()
        else:
            outputVoltage = None
            outputCurrent = None
        return Reading(state, setVoltage, setCurrent, outputVoltage, outputCurrent, commandsDone)

class mainWindow():
    def __init__(self):
        # initialize global variables
        self.outputOnOff = False
        self.ocpEnable = False
        self.ovpEnable = False
        # 'voltage' or 'current' while the user enters a value, otherwise None
        self.entryMode = None
        self.entryDigits = ''
        # waiting for the memory slot after the M key
        self.memorySelect = False
        self.lastReading = None
        self.controlsEnabled = False
        self.connectionMessage = ''
        self.messageTimer = None
        self.worker = None

        # initialize communication port
        self.psu = None
        portName = korad.find_port()
        if(portName is not None):
            try:
                self.psu = korad.KoradPSU(portName)
            except serial.SerialException as error:
                print(f"Cannot open communication port {portName}: {error}")


        # application window
        self.builder = Gtk.Builder()
        self.builder.add_from_file(GLADE_FILE)
        self.builder.connect_signals(self)

        cssProvider = Gtk.CssProvider()
        cssProvider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), cssProvider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.window = self.builder.get_object("mainWindow")
        # set window position
        self.window.set_position(Gtk.WindowPosition.CENTER)
        # set windows title
        self.window.set_title("KORAD DC POWER SUPPLY CONTROL")
        self.window.connect("key-press-event",self.on_key_press_event)
        self.window.connect("destroy", Gtk.main_quit)
        self.window.connect("delete-event", self.on_delete)


        # GUI labels
        self.labels = {
            "lblDisplayVoltage": self.builder.get_object("lblDisplayVoltage"),
            "lblDisplayCurrent": self.builder.get_object("lblDisplayCurrent"),
            "lblUserSetVoltage": self.builder.get_object("lblUserSetVoltage"),
            "lblUserSetCurrent": self.builder.get_object("lblUserSetCurrent"),
            "lblSerialPortStatus": self.builder.get_object("lblSerialPortStatus"),
        }

        # gui interface
        self.btnN0 = self.builder.get_object("btnN0")
        self.btnN1 = self.builder.get_object("btnN1")
        self.btnN2 = self.builder.get_object("btnN2")
        self.btnN3 = self.builder.get_object("btnN3")
        self.btnN4 = self.builder.get_object("btnN4")
        self.btnN5 = self.builder.get_object("btnN5")
        self.btnN6 = self.builder.get_object("btnN6")
        self.btnN7 = self.builder.get_object("btnN7")
        self.btnN8 = self.builder.get_object("btnN8")
        self.btnN9 = self.builder.get_object("btnN9")
        self.btnSetVoltage = self.builder.get_object("btnSetVoltage")
        self.btnSetCurrent = self.builder.get_object("btnSetCurrent")
        self.btnM1 = self.builder.get_object("btnM1")
        self.btnM2 = self.builder.get_object("btnM2")
        self.btnM3 = self.builder.get_object("btnM3")
        self.btnM4 = self.builder.get_object("btnM4")
        self.btnM5 = self.builder.get_object("btnM5")
        self.btnOVP = self.builder.get_object("btnOVP")
        self.btnOCP = self.builder.get_object("btnOCP")
        self.btnOutputOnOff = self.builder.get_object("btnOutputOnOff")

        # buttons that are usable only while the device is connected
        self.controls = [
            self.btnN0, self.btnN1, self.btnN2, self.btnN3, self.btnN4,
            self.btnN5, self.btnN6, self.btnN7, self.btnN8, self.btnN9,
            self.btnSetVoltage, self.btnSetCurrent,
            self.btnM1, self.btnM2, self.btnM3, self.btnM4, self.btnM5,
            self.btnOVP, self.btnOCP, self.btnOutputOnOff,
        ]


        self.btnN0.connect("clicked", self.clicked_Numeric, 0)
        self.btnN1.connect("clicked", self.clicked_Numeric, 1)
        self.btnN2.connect("clicked", self.clicked_Numeric, 2)
        self.btnN3.connect("clicked", self.clicked_Numeric, 3)
        self.btnN4.connect("clicked", self.clicked_Numeric, 4)
        self.btnN5.connect("clicked", self.clicked_Numeric, 5)
        self.btnN6.connect("clicked", self.clicked_Numeric, 6)
        self.btnN7.connect("clicked", self.clicked_Numeric, 7)
        self.btnN8.connect("clicked", self.clicked_Numeric, 8)
        self.btnN9.connect("clicked", self.clicked_Numeric, 9)
        self.btnSetVoltage.connect("clicked", self.clicked_setVoltage)
        self.btnSetCurrent.connect("clicked", self.clicked_setCurrent)
        self.btnM1.connect("clicked", self.clicked_Memory, 1)
        self.btnM2.connect("clicked", self.clicked_Memory, 2)
        self.btnM3.connect("clicked", self.clicked_Memory, 3)
        self.btnM4.connect("clicked", self.clicked_Memory, 4)
        self.btnM5.connect("clicked", self.clicked_Memory, 5)
        self.btnOVP.connect("clicked", self.clicked_OVP)
        self.btnOCP.connect("clicked", self.clicked_OCP)
        self.btnOutputOnOff.connect("clicked", self.clicked_outputOnOff)

        # keyboard shortcuts, digits are handled separately
        self.keyActions = {
            Gdk.KEY_o: lambda: self.clicked_outputOnOff(None),
            Gdk.KEY_v: lambda: self.clicked_setVoltage(None),
            Gdk.KEY_a: lambda: self.clicked_setCurrent(None),
            Gdk.KEY_m: self.startMemorySelect,
            Gdk.KEY_u: lambda: self.worker.requestUpdate(),
            Gdk.KEY_Return: self.confirmEntry,
            Gdk.KEY_KP_Enter: self.confirmEntry,
            Gdk.KEY_Escape: self.cancelEntry,
            Gdk.KEY_BackSpace: self.deleteDigit,
        }

        self.setConnectedState(False, 'The device is not connected or not turned on!')
        self.initDevice()

    # check if communication with the device is possible
    def isConnected(self):
        return self.controlsEnabled

    # enable or disable controls and show connection status
    def setConnectedState(self, connected, message):
        self.controlsEnabled = connected
        for control in self.controls:
            control.set_sensitive(connected)
        self.connectionMessage = message
        self.restoreStatus()

    # show a message in the status line for a few seconds
    def showMessage(self, message, timeout=MESSAGE_TIMEOUT):
        if(self.messageTimer is not None):
            GLib.source_remove(self.messageTimer)
        self.labels["lblSerialPortStatus"].set_text(message)
        self.messageTimer = GLib.timeout_add_seconds(timeout, self.restoreStatus)

    # show the connection status again
    def restoreStatus(self):
        if(self.messageTimer is not None):
            GLib.source_remove(self.messageTimer)
            self.messageTimer = None
        self.labels["lblSerialPortStatus"].set_text(self.connectionMessage)
        return False

    # add or remove a CSS class of a widget
    def setStyle(self, widget, styleClass, enabled):
        if(enabled):
            widget.get_style_context().add_class(styleClass)
        else:
            widget.get_style_context().remove_class(styleClass)

    # show output, OVP and OCP state on their buttons
    def updateButtonStates(self):
        self.setStyle(self.btnOutputOnOff, "active", self.outputOnOff)
        self.setStyle(self.btnOVP, "active", self.ovpEnable)
        self.setStyle(self.btnOCP, "active", self.ocpEnable)

    # disable controls after a communication error, the port is already closed
    def connectionLost(self, error):
        if(not self.controlsEnabled):
            return
        print(f"Communication error: {error}")
        self.setConnectedState(False, 'Connection to the device lost!')
        self.cancelEntry()
        self.memorySelect = False
        self.lastReading = None
        self.outputOnOff = False
        self.ovpEnable = False
        self.ocpEnable = False
        self.updateButtonStates()
        # do not leave stale values on the display
        self.labels["lblDisplayVoltage"].set_text("--V")
        self.labels["lblDisplayCurrent"].set_text("--A")
        self.labels["lblUserSetVoltage"].set_text("VSET: --V")
        self.labels["lblUserSetCurrent"].set_text("ISET: --A")

    # identify the device, enable controls and start periodic updates
    def initDevice(self):
        if(self.psu is None):
            return
        try:
            deviceID = self.psu.identify()
        except korad.ConnectionLostError as error:
            print(f"Communication error: {error}")
            return
        self.setConnectedState(True, f"{deviceID or 'Device'} connected via communication port: {self.psu.name}")
        self.worker = DeviceWorker(self.psu, self.updateDisplay, self.connectionLost)
        self.worker.start()

    # queue a command for the device
    def sendCommand(self, command):
        if(self.isConnected()):
            self.worker.submit(command)

    # function that resolve key press events
    def on_key_press_event(self, widget, event):
        if(not self.isConnected()):
            return False
        # leave shortcuts like Ctrl+Q or Alt+F4 to the window manager
        if(event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)):
            return False
        digit = DIGIT_KEYS.get(event.keyval)
        # M followed by 1-5 recalls a memory, any other key cancels it
        if(self.memorySelect):
            self.memorySelect = False
            self.restoreStatus()
            if(digit is not None and 1 <= digit <= MEMORY_SLOTS):
                self.clicked_Memory(None, digit)
            return True
        if(digit is not None):
            self.clicked_Numeric(None, digit)
            return True
        action = self.keyActions.get(event.keyval)
        if(action is None):
            return False
        action()
        return True

    # format a value for the display, or a placeholder if it is not available
    def formatValue(self, value, fmt, unit):
        if(value is None):
            return "--" + unit
        return fmt.format(value) + unit

    # show values read by the worker, called in the GUI thread
    def updateDisplay(self, reading):
        if(not self.isConnected()):
            return
        # a newer reading follows, this one could undo the last button press
        if(self.worker.isOutdated(reading)):
            return
        self.lastReading = reading
        # output, OVP and OCP can also be changed on the front panel
        if(reading.state is not None):
            self.outputOnOff = reading.state.output
            self.ovpEnable = reading.state.ovp
            self.ocpEnable = reading.state.ocp
        self.updateButtonStates()
        if(self.outputOnOff == True):
            displayVoltage = reading.outputVoltage
            displayCurrent = reading.outputCurrent
        else:
            displayVoltage = reading.setVoltage
            displayCurrent = reading.setCurrent
        # keep the value the user is entering
        if(self.entryMode != 'voltage'):
            self.labels["lblDisplayVoltage"].set_text(self.formatValue(displayVoltage, "{:05.2f}", "V"))
        if(self.entryMode != 'current'):
            self.labels["lblDisplayCurrent"].set_text(self.formatValue(displayCurrent, "{:05.3f}", "A"))
        self.labels["lblUserSetVoltage"].set_text("VSET: " + self.formatValue(reading.setVoltage, "{:05.2f}", "V"))
        self.labels["lblUserSetCurrent"].set_text("ISET: " + self.formatValue(reading.setCurrent, "{:05.3f}", "A"))
    #
    def on_delete(self, widget, data=None):
        if(self.worker is not None):
            # disable output before closing, queued after any pending commands
            self.sendCommand(lambda psu: psu.set_output(False))
            self.worker.stop()
            self.worker.join(timeout=3)
        if(self.psu is not None):
            self.psu.close()

    # start entering a voltage or current, the same button again cancels it
    def startEntry(self, mode):
        if(not self.isConnected()):
            return
        if(self.entryMode == mode):
            self.cancelEntry()
            return
        self.cancelEntry()
        setting = ENTRY_SETTINGS[mode]
        self.entryMode = mode
        self.entryDigits = ''
        self.setStyle(self.labels[setting.label], "editing", True)
        self.setStyle(self.builder.get_object(setting.button), "active", True)
        self.showEntry()

    # value of the digits entered so far
    def entryValue(self):
        return int(self.entryDigits or '0') / ENTRY_SETTINGS[self.entryMode].scale

    def showEntry(self):
        setting = ENTRY_SETTINGS[self.entryMode]
        self.labels[setting.label].set_text(setting.fmt.format(self.entryValue()) + setting.unit)

    # stop entering a value, the display shows the device values again
    def cancelEntry(self):
        if(self.entryMode is None):
            return
        setting = ENTRY_SETTINGS[self.entryMode]
        self.setStyle(self.labels[setting.label], "editing", False)
        self.setStyle(self.builder.get_object(setting.button), "active", False)
        self.entryMode = None
        self.entryDigits = ''
        if(self.lastReading is not None):
            self.updateDisplay(self.lastReading)

    # send the entered value to the device if it is within the device limits
    def confirmEntry(self):
        if(self.entryMode is None or self.entryDigits == ''):
            self.cancelEntry()
            return
        setting = ENTRY_SETTINGS[self.entryMode]
        value = self.entryValue()
        mode = self.entryMode
        self.cancelEntry()
        if(value > setting.maximum):
            self.showMessage(f"Value out of range, maximum is {setting.fmt.format(setting.maximum)}{setting.unit}")
            return
        if(mode == 'voltage'):
            self.sendCommand(lambda psu: psu.set_voltage(value))
        else:
            self.sendCommand(lambda psu: psu.set_current(value))
        # show the new value until the device confirms it
        self.labels[setting.label].set_text(setting.fmt.format(value) + setting.unit)

    def deleteDigit(self):
        if(self.entryMode is None):
            return
        self.entryDigits = self.entryDigits[:-1]
        self.showEntry()

    # wait for the memory slot number on the keyboard
    def startMemorySelect(self):
        self.memorySelect = True
        self.showMessage(f"Recall memory: press 1-{MEMORY_SLOTS}, any other key cancels")

    #
    def clicked_setVoltage(self, button):
        self.startEntry('voltage')

    #
    def clicked_setCurrent(self, button):
        self.startEntry('current')

    #
    def clicked_Numeric(self, button, data):
        if(not self.isConnected() or self.entryMode is None):
            return
        self.entryDigits = self.entryDigits + str(data)
        self.showEntry()
        if(len(self.entryDigits) == ENTRY_SETTINGS[self.entryMode].digits):
            self.confirmEntry()

    # recall settings from memory slot, output is disabled first
    def clicked_Memory(self, button, slot):
        self.cancelEntry()
        self.outputOnOff = False
        self.updateButtonStates()
        def recall(psu):
            psu.set_output(False)
            psu.recall(slot)
        self.sendCommand(recall)
        self.showMessage(f"Memory M{slot} recalled, output disabled")

    # output enable or disable
    def clicked_outputOnOff(self, button):
        self.outputOnOff = not self.outputOnOff
        self.updateButtonStates()
        enabled = self.outputOnOff
        self.sendCommand(lambda psu: psu.set_output(enabled))

    # ovp enable / disable
    def clicked_OVP(self, button):
        self.ovpEnable = not self.ovpEnable
        self.updateButtonStates()
        enabled = self.ovpEnable
        self.sendCommand(lambda psu: psu.set_ovp(enabled))

    # ocp enable / disable
    def clicked_OCP(self, button):
        self.ocpEnable = not self.ocpEnable
        self.updateButtonStates()
        enabled = self.ocpEnable
        self.sendCommand(lambda psu: psu.set_ocp(enabled))

if __name__ == '__main__':
    main = mainWindow()
    # show application window
    main.window.show()
    Gtk.main()
