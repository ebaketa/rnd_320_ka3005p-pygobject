# KORAD DC POWER SUPPLY CONTROL
## Python Application for controlling KORAD DC Power Supply 

**Hardware:**
- Linux PC
- Raspberry Pi
- RND LAB DC POWER SUPPLY
  (RND 320-KA3005P)

**Software:**
- Debian Linux OS
  (Or any other distribution)
- Raspberry Pi OS 
- Python 3 
- pyserial  
- PyGObject 
- pycairo 

## Installing Requirements:
On Debian and Raspberry Pi OS:
```
sudo apt install python3-gi gir1.2-gtk-3.0 python3-serial
```
Or with pip:
```
pip3 install -r requirements.txt
```
To access the serial port without root, add your user to the `dialout` group and log in again:
```
sudo usermod -a -G dialout $USER
```
## Cloning repository and Running program:
```
git clone https://github.com/ebaketa/rnd_320_ka3005p-pygobject.git
cd rnd_320_ka3005p-pygobject
python3 rnd_320_ka3005p-pygobject.py
```
Run the program from its directory and switch the power supply on before starting it.
