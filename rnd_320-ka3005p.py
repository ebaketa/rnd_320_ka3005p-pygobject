#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Program:      KORAD DC POWER SUPPLY CONTROL
# Author:       Elvis Baketa
# Device:       RND 320-KA3005P
#               Python 2.7.16
#               PyGObject
#               PySerial

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
        # application window
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
        self.ocpEnable = False
        self.ovpEnable = False
        self._userSetVoltage = 0.00
        self._userSetCurrent = 0.000
        self._activeSetVoltage = False
        self._activeSetCurrent = False
        self.temp_setVoltage = ''
        self.temp_setCurrent = ''

        # gui interface
        self.lblDisplayVoltage = self.builder.get_object("lblDisplayVoltage")
        self.lblDisplayCurrent = self.builder.get_object("lblDisplayCurrent")
        self.lblUserSetVoltage = self.builder.get_object("lblUserSetVoltage")
        self.lblUserSetCurrent = self.builder.get_object("lblUserSetCurrent")
        self.lblSerialPortStatus = self.builder.get_object("lblSerialPortStatus")
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
        self.btnPowerOnOff = self.builder.get_object("btnPowerOnOff")
        self.btnOVP = self.builder.get_object("btnOVP")
        self.btnOCP = self.builder.get_object("btnOCP")
        self.btnOutputOnOff = self.builder.get_object("btnOutputOnOff")
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
        self.btnM1.connect("clicked", self.clicked_M1)
        self.btnM2.connect("clicked", self.clicked_M2)
        self.btnM3.connect("clicked", self.clicked_M3)
        self.btnM4.connect("clicked", self.clicked_M4)
        self.btnOVP.connect("clicked", self.clicked_OVP)
        self.btnOCP.connect("clicked", self.clicked_OCP)
        self.btnOutputOnOff.connect("clicked", self.clicked_btnOutputOnOff)

        # show application window
        # self.window.show()

    # function to prepare the program for start
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
                    # send command to get device identification
                    self.communicationPort.write("*IDN?")
                    time.sleep(0.15)
                    # read device identification
                    self._getDeviceIdentification = self.communicationPort.read(self.communicationPort.in_waiting)
                    self.lblSerialPortStatus.set_text(self._getDeviceIdentification + ' connected via communication port: ' + serialPortValid)
                    self.powerOnOff = True
        elif(self.serialPortAvailable == False):
            self.lblSerialPortStatus.set_text('Device not connected!')
        else:
            print('Unknown error!')

        # update display
        self.updateDisplay()

    # device identification
    def getDeviceID(self):
        self.communicationPort.write("*IDN?")
        time.sleep(0.1)
        deviceID = self.communicationPort.read(self.communicationPort.in_waiting)
        return deviceID

    # device status
    def getDeviceStatus(self):
        self.communicationPort.write("STATUS?")
        time.sleep(0.1)
        deviceStatus = self.communicationPort.read(self.communicationPort.in_waiting)
        return deviceStatus.encode('hex')

    # update display
    def updateDisplay(self):
        if(self.powerOnOff == True and self.outputOnOff == True):
            self.lblDisplayVoltage.set_text("{:05.2f}".format(self.actualOutputVoltage()) + "V")
            self.lblDisplayCurrent.set_text("{:05.3f}".format(self.actualOutputCurrent()) + "A")
            self.lblUserSetVoltage.set_text("{:05.2f}".format(self.userSetVoltage()) + "V")
            self.lblUserSetCurrent.set_text("{:05.3f}".format(self.userSetCurrent()) + "A")
        elif(self.powerOnOff == True and self.outputOnOff == False):
            self.lblDisplayVoltage.set_text("{:05.2f}".format(self.userSetVoltage()) + "V")
            self.lblDisplayCurrent.set_text("{:05.3f}".format(self.userSetCurrent()) + "A")
            self.lblUserSetVoltage.set_text("{:05.2f}".format(self.userSetVoltage()) + "V")
            self.lblUserSetCurrent.set_text("{:05.3f}".format(self.userSetCurrent()) + "A")
        else:
            print("Unknown error!")

    def on_delete(self, widget, data=None):
        # only close port if it is available
        if(self.serialPortAvailable == True and self.communicationPort.is_open):
            self.communicationPort.close()

    # 
    def clicked_setVoltage(self, button):
        self._userSetVoltage = 0.00
        self._activeSetVoltage = not self._activeSetVoltage
        if(self._activeSetVoltage == True):
            self.btnSetVoltage.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0,0,128));
        elif(self._activeSetVoltage == False):
            self.btnSetVoltage.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("#333333"))

    # 
    def clicked_setCurrent(self, button):
        self._userSetCurrent = 0.000
        self._activeSetCurrent = not self._activeSetCurrent

    # 
    def clicked_Numeric(self, button, data):
        if(self._activeSetVoltage == True):
            self.temp_setVoltage = self.temp_setVoltage + str(data)
            self._userSetVoltage = float(self.temp_setVoltage)
            self._userSetVoltage = self._userSetVoltage / 100
            self._userSetVoltage = ("{:05.2f}".format(self._userSetVoltage))
            self.lblDisplayVoltage.set_text(self._userSetVoltage + "V")
            if(len(self.temp_setVoltage) == 4):
                self.writeUserSetVoltage()
                self.updateDisplay()
                self._activeSetVoltage = False
                self.temp_setVoltage = ''
        elif(self._activeSetCurrent == True):
            self.temp_setCurrent = self.temp_setCurrent + str(data)
            self._userSetCurrent = float(self.temp_setCurrent)
            self._userSetCurrent = self._userSetCurrent / 1000
            self._userSetCurrent = ("{:05.3f}".format(self._userSetCurrent))
            self.lblDisplayCurrent.set_text(self._userSetCurrent + "A")
            if(len(self.temp_setCurrent) == 4):
                self.writeUserSetCurrent()
                self.updateDisplay()
                self._activeSetCurrent = False
                self.temp_setCurrent = ''
        else:
            pass

    # 
    def clicked_M1(self, button):
        self.disableOutput()
        self.communicationPort.write("RCL1")
        time.sleep(0.15)
        self.updateDisplay()

    # 
    def clicked_M2(self, button):
        self.disableOutput()
        self.communicationPort.write("RCL2")
        time.sleep(0.15)
        self.updateDisplay()

    # 
    def clicked_M3(self, button):
        self.disableOutput()
        self.communicationPort.write("RCL3")
        time.sleep(0.15)
        self.updateDisplay()

    # 
    def clicked_M4(self, button):
        self.disableOutput()
        self.communicationPort.write("RCL4")
        time.sleep(0.15)
        self.updateDisplay()

    # output enable or disable
    def clicked_btnOutputOnOff(self, button):
        self.outputOnOff = not self.outputOnOff
        if(self.outputOnOff == False):
            self.communicationPort.write("OUT0")
            time.sleep(0.15)
        elif(self.outputOnOff == True):
            self.communicationPort.write("OUT1")
            time.sleep(0.15)
        else:
            print("Unknown error!")
        # update display
        self.updateDisplay()

    # ovp enable / disable
    def clicked_OVP(self, button):
        self.ovpEnable = not self.ovpEnable
        if(self.ovpEnable == True):
            self.communicationPort.write("OVP1")
        elif(self.ovpEnable == False):
            self.communicationPort.write("OVP0")
        else:
            print("Unknown error!")
        time.sleep(0.15)

    # ocp enable / disable
    def clicked_OCP(self, button):
        self.ocpEnable = not self.ocpEnable
        if(self.ocpEnable == True):
            self.communicationPort.write("OCP1")
        elif(self.ocpEnable == False):
            self.communicationPort.write("OCP0")
        else:
            print("Unknown error!")
        time.sleep(0.15)

    # fetch an current user set voltage
    def userSetVoltage(self):
        self.communicationPort.write("VSET1?")
        time.sleep(0.15)
        _userSetVoltage = self.communicationPort.read(self.communicationPort.in_waiting)
        # _userSetVoltage = _userSetVoltage.encode('ascii')

        return float(_userSetVoltage)

    # fetch an current user set current
    def userSetCurrent(self):
        self.communicationPort.write("ISET1?")
        time.sleep(0.15)
        _userSetCurrent = self.communicationPort.read(self.communicationPort.in_waiting)

        return float(_userSetCurrent)

    # fetch an actual output voltage
    def actualOutputVoltage(self):
        self.communicationPort.write("VOUT1?")
        time.sleep(0.15)
        _actualOutputVoltage = self.communicationPort.read(self.communicationPort.in_waiting)

        return float(_actualOutputVoltage)

    # fetch an actual output current
    def actualOutputCurrent(self):
        self.communicationPort.write("IOUT1?")
        time.sleep(0.15)
        _actualOutputCurrent = self.communicationPort.read(self.communicationPort.in_waiting)

        return float(_actualOutputCurrent)

    # write an current user set voltage
    def writeUserSetVoltage(self):
        self.communicationPort.write("VSET1:" + self._userSetVoltage.encode('ascii'))
        time.sleep(0.15)

    # write an current user set current
    def writeUserSetCurrent(self):
        self.communicationPort.write("ISET1:" + self._userSetCurrent.encode('ascii'))
        time.sleep(0.15)

    # output disable
    def disableOutput(self):
        self.outputOnOff = False
        self.communicationPort.write("OUT0")
        time.sleep(0.15)
        

if __name__ == '__main__':
    main = mainWindow()
    # show application window
    main.window.show()
    Gtk.main()

