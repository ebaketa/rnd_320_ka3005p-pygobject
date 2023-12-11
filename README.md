# KORAD DC POWER SUPPLY CONTROL
## Python Application for controlling KORAD DC Power Supply 

**Hardware:**
- PC Linux
- Raspberry Pi
- RND LAB DC POWER SUPPLY
  (RND 320-KA3005P)

**Software:**
- Debian Linux OS
  (Or any other distribution)
- Raspberry Pi OS 
- Python 3.11.2 
- pyserial 3.5 
- PyGObject  3.46.0 
- pycairo    1.25.1 

## Installing PySerial:
```
# python version 2
sudo apt install python-serial

# python version 3
sudo apt install python3-serial
```
## Installing PyGObject:
```
# python version 2
sudo apt install python-gi python-gi-cairo gir1.2-gtk-3.0

# python version 3
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
```
## Cloning repository and Running program:
```
git clone https://github.com/ebaketa/rnd_320-ka3005p.git

python ./rnd_320-ka3005p.py
```
