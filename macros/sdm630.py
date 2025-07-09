#!/bin/python3




import datetime
import time
import webiopi
import sys
import struct
import logging
import pymodbus.client.serial
import sdm_modbus
import threading

from pysnmp.hlapi import *
from flask import Flask
sys.path.insert(0,"/home/pi/webiopi/macros")
from Basics  import *
from webiopi.utils.types import values
from pymodbus.register_read_message import ReadInputRegistersResponse
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

GPIO = webiopi.GPIO
level = "init"
power = "init"
rpm = "init"
deltaForAction = 1
lastAction = None
impulsdauer = 3
impulsstart = 0
 
aktuellerSollwert = 40
aktuellesZeitfenster = 1800
automationActive = "on"

#global app = Flask(__name__)
l_result = []




cl0 = pymodbus.client.ModbusSerialClient( port='/dev/ttyUSB0', baudrate=9600, parity='N',stopbits=1, timeout=1)
cl1 = pymodbus.client.ModbusSerialClient( port='/dev/ttyUSB1', baudrate=9600, parity='N',stopbits=1, timeout=1)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = False
# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
#ch = logging.FileHandler(r'/var/log/turbine.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
try:
    ch = logging.FileHandler('/var/log/turbine.log')
    
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
except (PermissionError, OSError) as e:
    fallback = logging.StreamHandler(sys.stdout)
    fallback.setLevel(logging.DEBUG)
    fallback.setFormatter(formatter)
    logger.addHandler(fallback)
    logger.warning(f"Logging to file failed: {e}. Falling back to STDOUT.")
fh = logging.StreamHandler(sys.stdout)

# create formatter


# add formatter to ch
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)
logger.addHandler(fh)

waterlevel = Level(300,"level",logger) #maxage
powerlevel = Level(100,"power",logger) #maxage
def loop():
    while (True):
     read_sdm630()
     print (values)
     webiopi.sleep(0.5)


        #print ("i: " +str(i) + "; " + "index: "+ str(increment) +"; " +str(resp.getRegister(increment)/(10**lregs[increment][3])))
        #values[lregs[i][0]]=resp.getRegister(i)/(10**lregs[i][3])
     #index = 0
     #for reg in lregs:
     #   values[reg[0]]=resp.getRegister(index + lregs[len(lregs)-1][1]-lregs[index][1])/reg[3]
     #   index += 1
     #print ("Myvalues" +str(values))

def read_sdm630 ( ):
    meter = sdm_modbus.SDM630(
        device='/dev/ttyUSB1',
        stopbits=1,
        parity='N',
        baud=9600,
        timeout=1,
        unit=1
    )
    lst = ['l1_power_active','l2_power_active','l3_power_active','total_power_active','import_energy_active','export_energy_reactive','frequency']
    global values 
    for k, v in meter.read_all(sdm_modbus.registerType.INPUT).items():
        address, length, rtype, dtype, vtype, label, fmt, batch, sf = meter.registers[k]
        if ( any(k in x for x in lst) ):
           values['sdm630_'+k]=v
# Using the special variable 
# __name__
if __name__=="__main__":


    loop()
    #logger.debug(f"l_result  {l_result}")
    #logger.debug("Starting main")
    #wl=Level(5,"level",logger)
    #for i in range(10):
    #    wl.addLevel(46)
    #    time.sleep(1)
   # wl.addLevel(time.time()-4,42)
   # wl.isStable()
    #logger.debug(str(wl))
    #loop()
   
   

        
  
