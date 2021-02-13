#!/usr/bin/env python
# -*- coding: utf-8 -*-

# RND 320-KA3005P
# Python 2.7.16
# PyGObject
# PySerial

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango

import serial
import serial.tools.list_ports
import time

class mainWindow():
    def __init__(self):
        gladeFile = "rnd_320-ka3005p.glade"
        self.builder = Gtk.Builder()
        self.builder.add_from_file(gladeFile)
        self.builder.connect_signals(self)
        self.window = self.builder.get_object("mainWindow")
        # set window position
        self.window.set_position(Gtk.WindowPosition.CENTER)
        # set windows title
        self.window.set_title("KORAD DC POWER SUPPLY CONTROL")
        self.window.connect("destroy", Gtk.main_quit)
        self.window.connect("delete-event", self.on_delete)
        self.window.connect("realize", self.on_realize)

        # global variables
        self.powerOnOff = False
        self.outputOnOff = False

        # gui interface
        self.lblSerialPortStatus = self.builder.get_object("lblSerialPortStatus")
        self.btnPowerOnOff = self.builder.get_object("btnPowerOnOff")
        self.btnOutputOnOff = self.builder.get_object("btnOutputOnOff")
        self.btnOutputOnOff.connect("clicked", self.on_btnOutputOnOff_clicked)

        # show application window
        # self.window.show()

    def on_realize(self, widget, data=None):
        # get list of serial ports
        serialPortList = serial.tools.list_ports.comports()

        # get count of available serial ports
        serialPortCount = len(serialPortList)

        # set serial port available
        if(serialPortCount > 0):
            self.serialPortAvailable = True
        else:
            self.serialPortAvailable = False
        
        if(self.serialPortAvailable == True):
            # check all listed ports
            for serialPort in serialPortList:
                # check if valid serial port exist (VID=1046, PID=20497)
                if(serialPort.vid == 1046 and serialPort.pid == 20497):
                    # set valid serial port for communication
                    serialPortValid = serialPort.device
                    # open valid serial port for communication
                    self.communicationPort = serial.Serial(serialPortValid)
                    # check if communication port is open
                    self.communicationPort.write("*IDN?")
                    time.sleep(0.15)
                    # get psu identification id
                    self._getDeviceIdentification = self.communicationPort.read(self.communicationPort.in_waiting)
                    self.lblSerialPortStatus.set_text(self._getDeviceIdentification + ' connected via communication port: ' + serialPortValid)
        elif(self.serialPortAvailable == False):
            self.lblSerialPortStatus.set_text('Device not connected!')
        else:
            print('Unknown error!')
        # update display
        self.updateDisplay()

    def updateDisplay(self):
        pass

    def on_delete(self, widget, data=None):
        # only close port if it is available
        if(self.serialPortAvailable == True and self.communicationPort.is_open):
            self.communicationPort.close()

    def on_btnOutputOnOff_clicked(self, button):
        self.outputOnOff = not self.outputOnOff
        if(self.outputOnOff == False):
            self.communicationPort.write("OUT0")
            time.sleep(0.1)
        elif(self.outputOnOff == True):
            self.communicationPort.write("OUT1")
            time.sleep(0.1)
        else:
            print("Unknown error!")

if __name__ == '__main__':
    main = mainWindow()
    # show application window
    main.window.show()
    Gtk.main()

