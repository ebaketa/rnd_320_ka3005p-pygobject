# KORAD DC POWER SUPPLY CONTROL
## Python Application for controlling KORAD DC Power Supply

GTK 3 application for controlling the RND 320-KA3005P (KORAD KA3005P)
laboratory power supply over its USB serial port.

- set voltage (up to 30.00 V) and current (up to 5.000 A)
- switch the output, OVP and OCP on and off
- recall memories M1-M5 (the output is switched off first)
- live display of the measured output voltage and current
- changes made on the front panel are shown in the application
- the output is switched off when the application is closed

**Hardware:**
- Linux PC or Raspberry Pi
- RND LAB DC POWER SUPPLY (RND 320-KA3005P), tested with firmware V2.0

**Software:**
- Debian, Raspberry Pi OS or another Linux distribution
- Python 3
- PyGObject (GTK 3), pycairo, pyserial

## Installing requirements

System packages (Debian / Raspberry Pi OS):
```
sudo apt install python3-venv gir1.2-gtk-3.0 fonts-inconsolata \
    libgirepository1.0-dev libcairo2-dev pkg-config python3-dev
```

Your user needs access to the serial port, which on Debian is given by the
`dialout` group (log out and back in afterwards):
```
sudo usermod -aG dialout $USER
```

## Cloning repository and running program
```
git clone https://github.com/ebaketa/rnd_320_ka3005p-pygobject.git
cd rnd_320_ka3005p-pygobject
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python rnd_320_ka3005p-pygobject.py
```

The power supply is found automatically by its USB ID (VID 0x0416, PID 0x5011).
Switch it on before starting the program.

To skip building PyGObject, install `python3-gi` and `python3-serial` with apt
and create the environment with `python3 -m venv --system-site-packages .venv`,
or run the program with the system `python3` directly.

## Usage

Press **V** or **A** and enter the digits; they fill the value from the right,
so 1, 2, 3, 4 gives 12.34 V. The value is sent after the fourth digit or with
Enter. Values above the device limits are rejected.

| Key | Action |
|---|---|
| `0`-`9` | enter digits (keypad works too) |
| `v` / `a` | enter voltage / current, pressing again cancels |
| Enter | send the entered value |
| Backspace | delete the last digit |
| Esc | cancel the entry |
| `m` then `1`-`5` | recall memory M1-M5 |
| `o` | output on / off |
| `u` | update the display now |

Active output, OVP and OCP buttons are shown in green.

## Running tests
```
.venv/bin/python -m unittest discover -s tests
```

The tests use a simulated serial port, no device is needed.
