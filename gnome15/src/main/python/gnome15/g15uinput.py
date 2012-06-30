#        +-----------------------------------------------------------------------------+
#        | GPL                                                                         |
#        +-----------------------------------------------------------------------------+
#        | Copyright (c) Brett Smith <tanktarta@blueyonder.co.uk>                      |
#        |                                                                             |
#        | This program is free software; you can redistribute it and/or               |
#        | modify it under the terms of the GNU General Public License                 |
#        | as published by the Free Software Foundation; either version 2              |
#        | of the License, or (at your option) any later version.                      |
#        |                                                                             |
#        | This program is distributed in the hope that it will be useful,             |
#        | but WITHOUT ANY WARRANTY; without even the implied warranty of              |
#        | MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the               |
#        | GNU General Public License for more details.                                |
#        |                                                                             |
#        | You should have received a copy of the GNU General Public License           |
#        | along with this program; if not, write to the Free Software                 |
#        | Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA. |
#        +-----------------------------------------------------------------------------+

"""
Manages the use of uinput to inject input events (key presses, mouse movement,
joystick events) into the kernel.
"""
        
import logging
import uinput
import g15util
import os
import subprocess
from uinput.ev import *
from threading import RLock
from gnome15 import g15globals
logger = logging.getLogger("uinput")

MOUSE = "mouse"
JOYSTICK = "joystick"
DIGITAL_JOYSTICK = "digital-joystick"
KEYBOARD = "keyboard"
DEVICE_TYPES = [ MOUSE, KEYBOARD, JOYSTICK, DIGITAL_JOYSTICK ]

#capabilities = uinput.capabilities.CAPABILITIES
capabilities = uinput.ev.__dict__
registered_parameters = { MOUSE: {}, 
                   JOYSTICK:  {
                    uinput.ABS_X: (0, 255, 0, 0),
                    uinput.ABS_Y: (0, 255, 0, 0),
                             }, 
                   DIGITAL_JOYSTICK:  {
                    uinput.ABS_X: (0, 255, 0, 0),
                    uinput.ABS_Y: (0, 255, 0, 0),
                             }, 
                   KEYBOARD: {} }
uinput_devices = {}
locks = {}
for t in DEVICE_TYPES:
    locks[t] = RLock()

"""
These are the very unofficial vendor / produce codes used for the virtual
devices 
"""
GNOME15_USB_VENDOR_ID = 0xdd55
GNOME15_MOUSE_PRODUCT_ID = 0x0001
GNOME15_JOYSTICK_PRODUCT_ID = 0x0002
GNOME15_KEYBOARD_PRODUCT_ID = 0x0003
GNOME15_DIGITAL_JOYSTICK_PRODUCT_ID = 0x0004

"""
python-uinput currently doesn't expose these constants
"""

EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03

"""
special virtual keys that are actually joystick movement
"""
JS = 0x9999
JS_LEFT = 0x9701
JS_RIGHT = 0x9702
JS_DOWN = 0x9703
JS_UP = 0x9704
JS_MOVEMENT = {
                    "X_LEFT"    : (JS, JS_LEFT), 
                    "X_RIGHT"   : (JS, JS_RIGHT),
                    "Y_UP"      : (JS, JS_UP),
                    "Y_DOWN"    : (JS, JS_DOWN),
}
for k in JS_MOVEMENT:
    capabilities[k] = JS_MOVEMENT[k]
    
def are_calibration_tools_available():
    """
    Test for the existence of calibration tools 'jstest-gtk' and 'jscal'.
    """
    return os.system("which jstest-gtk >/dev/null") == 0 and os.system("which jscal >/dev/null") == 0
    
def open_devices():
    """
    Initialize, opening all devices
    """
    __check_devices()
    
def close_devices():
    """
    Clean up, closing all the devices
    """
    for device_type in DEVICE_TYPES:
        if device_type in uinput_devices:
            logger.debug("Closing UINPUT device %s" % device_type)
            del uinput_devices[device_type]
            
def calibrate(device_type):
    """
    Run external joystick calibration utility
    
    Keyword arguments:
    device_type    --    device type
    """
    if are_calibration_tools_available():
        if not device_type in [ JOYSTICK, DIGITAL_JOYSTICK ]:
            raise Exception("Cannot calibrate this device type (%s)" % device_type)
        device_file = get_device(device_type)
        if device_file:
            load_calibration(device_type)
            g15util.mkdir_p(os.path.expanduser("~/.config/gnome15"))
            os.system("jstest-gtk '%s'" % (device_file))
            save_calibration(device_type)
        
def save_calibration(device_type):
    """
    Run external joystick calibration utility
    
    Keyword arguments:
    device_type    --    device type
    """
    if are_calibration_tools_available():
        if not device_type in [ JOYSTICK, DIGITAL_JOYSTICK ]:
            raise Exception("Cannot calibrate this device type (%s)" % device_type)
        device_file = get_device(device_type)
        if device_file:
            proc = subprocess.Popen(["jscal", "-q", device_file ], stdout=subprocess.PIPE) 
            out = proc.communicate()[0]
            js_config_file = "%s/%s.js" % ( os.path.expanduser("~/.config/gnome15"), device_type )
            g15util.mkdir_p(os.path.expanduser("~/.config/gnome15"))
            f = open(js_config_file, "w")
            try :
                f.write(out)
            finally :
                f.close()
        
def load_calibration(device_type):
    """
    Run external joystick calibration utility
    
    Keyword arguments:
    device_type    --    device type
    """
    if are_calibration_tools_available():
        if not device_type in [ JOYSTICK, DIGITAL_JOYSTICK ]:
            raise Exception("Cannot calibrate this device type (%s)" % device_type)
        device_file = get_device(device_type)
        if device_file:
            js_config_file = "%s/%s.js" % ( os.path.expanduser("~/.config/gnome15"), device_type )
            if os.path.exists(js_config_file):
                f = open(js_config_file, "r")
                try :
                    cal = f.readline().split()
                    logger.info("Calibrating using '%s'" % cal) 
                    proc = subprocess.Popen(cal, stdout=subprocess.PIPE) 
                    logger.info("Calibrated. %s" % proc.communicate()[0])
                except Exception as e:
                    logger.error("Failed to calibrate joystick device. %s" % e)
                finally :
                    f.close()
            else:
                logger.warn("No joystick calibration available.")

            
def get_device(device_type):
    """
    Find the actual input device given the virtual device type
    
    Keyword arguments:
    device_type    --    device type
    """
    vi_path = "/sys/devices/virtual/input"
    if os.path.exists(vi_path):
        for p in os.listdir(vi_path):
            dev_dir = "%s/%s" % (vi_path, p)
            name_file = "%s/name" % (dev_dir)
            if os.path.exists(name_file):
                f = open(name_file, "r")
                try :
                    device_name = f.readline().replace("\n", "")
                    if device_name == "gnome15-%s" % device_type:
                        dev_files = os.listdir(dev_dir)
                        for dp in dev_files:
                            if dp.startswith("js"):
                                return "/dev/input/%s" % dp
                        for dp in dev_files:
                            if dp.startswith("event"):
                                return "/dev/input/%s" % dp
                finally :
                    f.close() 
                
    
def syn(target):
    """
    Emit the syn.
    
    Keyword arguments:
    target         --    target device type (MOUSE, KEYBOARD or JOYSTICK).
    """
    uinput_devices[target].syn()
    
def emit(target, code, value, syn=True):
    """
    Emit an input event, optionally emit a SYN as well
    
    Keyword arguments:
    target         --    The target device type (MOUSE, KEYBOARD or JOYSTICK)
                         type code.
    code           --    uinput code (either single code, where type will be 
                         determined by target or a tuple consisting of event
                         type and event code)
    value          --    uinput value
    syn            --    emit SYN (defaults to True)
    """
    if not target in DEVICE_TYPES:
        raise Exception("Invalid target. '%s' must be one of %s" % (target, str(DEVICE_TYPES)))
    
    if not isinstance(code, tuple):
        if target == MOUSE and code in [ uinput.REL_X[1], uinput.REL_Y[1] ]:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("UINPUT mouse event at %s, code = %s, val = %d, syn = %s" % ( target, code, value, str(syn) ) )
            code = ( EV_REL, code )            
        elif ( target == JOYSTICK or target == DIGITAL_JOYSTICK ):
            if code == JS_LEFT:
                value = 0 if value > 0 else 128
                code = ABS_X
            elif code == JS_RIGHT:
                value = 255 if value > 0 else 128
                code = ABS_X
            elif code == JS_UP:
                value = 0 if value > 0 else 128
                code = ABS_Y
            elif code == JS_DOWN:
                value = 255 if value > 0 else 128
                code = ABS_Y
            code = (EV_ABS, code)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("UINPUT joystick event at %s, code = %s, val = %d, syn = %s" % ( target, code, value, str(syn) ) )
        else: 
            code = ( EV_KEY, code )
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("UINPUT uinput keyboard event at %s, code = %s, val = %d, syn = %s" % ( target, code, value, str(syn) ) )
    
    locks[target].acquire()
    try:
        uinput_devices[target].emit( code, value, syn)
    finally:
        locks[target].release()
    
def __get_keys(prefix, exclude = None):
    l = []
    for k in sorted(capabilities.iterkeys()):
        if k.startswith(prefix) and ( exclude == None or not k.startswith(exclude) ):
            l.append(capabilities[k])
    return l

def get_keys(device_type):
    if device_type == MOUSE:
        return __get_keys("BTN_", "BTN_TOOL_")
    elif device_type == JOYSTICK:
        return __get_keys("BTN_", "X_", "Y_")
    else:
        return __get_keys("KEY_")

def get_buttons(device_type, real_uinput_only = False):
    fname = os.path.join(g15globals.ukeys_dir, "%s.keys" % device_type)
    f = open(fname, "r")
    b = []
    for line in f.readlines():
        line = line.strip()
        if not line == "" and not line.startswith("#"):
            if line in capabilities:
                b.append((line, capabilities[line][1]))
            else:
                logger.warning("Invalid key name '%s' in %s" % (line, fname))
    return b
    
def __check_devices():
    for device_type in DEVICE_TYPES:
        if not device_type in uinput_devices:
            logger.info("Opening uinput device for %s" % device_type)
            keys = []
            for b, _ in get_buttons(device_type, True):
                if capabilities[b][0] < 0x9999:
                    keys.append(capabilities[b])
            
            if device_type == MOUSE:
                virtual_product_id = GNOME15_MOUSE_PRODUCT_ID
                keys.append((REL_X[0], REL_X[1], 0, 255, 0, 0))
                keys.append((REL_Y[0], REL_Y[1], 0, 255, 0, 0))
            elif device_type == JOYSTICK:
                virtual_product_id = GNOME15_JOYSTICK_PRODUCT_ID
                keys.append((ABS_X[0], ABS_X[1], 0, 255, 0, 0))
                keys.append((ABS_Y[0], ABS_Y[1], 0, 255, 0, 0))
            elif device_type == DIGITAL_JOYSTICK:
                virtual_product_id = GNOME15_JOYSTICK_PRODUCT_ID
                keys.append((ABS_X[0], ABS_X[1], 0, 255, 0, 0))
                keys.append((ABS_Y[0], ABS_Y[1], 0, 255, 0, 0))
            else:
                virtual_product_id = GNOME15_KEYBOARD_PRODUCT_ID
                
            caps = tuple(keys)    
            uinput_device = uinput.Device(name="gnome15-%s" % device_type,
                                          events  = caps,
                                          vendor = GNOME15_USB_VENDOR_ID,
                                          product = virtual_product_id)                                
            uinput_devices[device_type] = uinput_device
            
            # Centre the joystick by default
            if device_type == JOYSTICK or device_type == DIGITAL_JOYSTICK:
                syn(device_type)
                load_calibration(device_type)
                emit(device_type, ABS_X, 128, False)
                emit(device_type, ABS_Y, 128, False)
            else:
                emit(device_type, 0, 0)
                emit(device_type, 0, 1)
            
            