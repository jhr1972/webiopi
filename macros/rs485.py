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

app = Flask(__name__)
level = "init"
power = "init"
rpm = "init"
deltaForAction = 1
lastAction = None
impulsdauer = 1.5
impulsstart = 0
l_result = []

aktuellerSollwert = 40
aktuellesZeitfenster = 1800
automationActive = "on"

sensor = [
   ( 'c1'     ,0x03, '%6.1f',1 )  #sensor c1 
]

regs = [
   ( 'P1'     ,0x0c, '%6.2f',2 ), # Active Power ("Wirkleistung") Phase 1 [W]
   ( 'P2'     ,0x000e, '%6.2f',2 ), # Active Power ("Wirkleistung") Phase 2 [W]
   ( 'P3'     ,0x0010, '%6.2f',2 ), #  Active Power ("Wirkleistung") Phase 3 [W]
   ( 'Ca'     ,0x64, '%6.2f',2), # Current Phase A[A]
   ( 'Cb'     ,0x65, '%6.2f',2 ), # Current Phase B[A]
   ( 'Cc'     ,0x66, '%6.2f',2 ), # Current Phase C[A]
   ( 'Pa_active',0x67, '%6.3f',3 ), # Active Power ("Wirkleistung") Phase A [W]
   ( 'Pb_active',0x68, '%6.3f',3 ), # Active Power ("Wirkleistung") Phase B [W]
   ( 'Pc_active',0x69, '%6.3f',3 ), # Active Power ("Wirkleistung") Phase C [W]
   ( 'P_active' ,0x6A, '%6.3f',0 ), # Active Power ("Wirkleistung") Total [W]
   ( 'Freq'   ,0x77, '%6.2f',2 )  # Line Frequency [Hz]         

]

double_regs = [
        # Symbol    Reg#  Format
         ( 'Pa_compl'     , 0x164, '%6.2f',2 ), # Active Power with complement
         ( 'Pb_compl'     ,0x166, '%6.1f',1 ), # Active Power with complement
         ( 'Pc_compl'     ,0x168, '%6.1f',1 ), # Active Power with complement
         ( 'P_compl'     ,0x16A, '%6.1f',1 ) # Active Total Power with complement
]

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
    g = bulkCmd(
            SnmpEngine(),
            CommunityData('public'),
            UdpTransportTarget(('192.168.100.177', 161)),
            ContextData(),
            0,100,
            # fetch up to 25 OIDs one-shot
            ObjectType(ObjectIdentity('1.3.6.1.4.1.13576.10.1.100.1.1.3.0'))
        )
    i = 0
    global l_result
    if len(l_result) == 0:
       l = 0
       while ( l < 100 ):
          l_result.append("")
          l+=1
            
    #l_result.clear() #empties list
    while ( i < 100 ):
      result = next(g)
      # print(str(result[3][0]))
      #l_result[i]=str(result[3][0]).split('=')[1]
      l_result[i]=str(result[3][0]).split('=')[1]
      
      if ( i == 71):
          global rpm
          rpm = str(result[3][0]).split('=')[1]
          #print("Rpm:", rpm)
          values["turbine_rpm"]=rpm
          
      if ( i == 72):
          global level 
          level = str(result[3][0]).split('=')[1]
          values["turbine_level"]=level
          #print("Level:", level)
      if ( i == 73):
          global power
          power = str(result[3][0]).split('=')[1]
          powerlevel.addLevel (int(power))
          values["turbine_currentpower"]=power
          values["turbine_averagepower"]=str(round(powerlevel.getAverageValues()))
          
          #print("Power:", power)
      i = i+1
    global waterlevel
    waterlevel.addLevel(level)
   
    read_bulk(cl1,regs)
    read_double_bulk(cl1,double_regs)
    
    read_sdm530(cl0)
    #print (values)
 
    webiopi.sleep(2)


def read_double_bulk (client, lregs ):
    print(f"Aktive Threads: {threading.active_count()}")
    print("Thread-Übersicht:")
    for thread in threading.enumerate():
        print(f" - {thread.name}")
    bulklen=(lregs[len(lregs)-1][1]-lregs[0][1]+2)
    #print ("Bulklen: " +str(bulklen))
    try:
        resp = client.read_holding_registers(lregs[0][1],count=bulklen, slave=24)
        if (resp.function_code >= int('0x80',16)):
           print ("Received error code %",resp.function_code)
           return
        print(str(resp.registers))

        global values
        i=0
        regcounter=0
        increment=0

        while i < len(lregs):
           #print ("i: " + str(i) + " regcounter: " +str(regcounter) + " getRegister: " + str(resp.getRegister(regcounter)))
           print (f"i: %d, content: %s" %  ( i, str(resp.getRegister(regcounter))))
           print (f"i+1: %d, content: %s" %  ( i+1, str(resp.getRegister(regcounter+1))))
           value=struct.unpack('>i',struct.pack('>HH',resp.getRegister(regcounter),resp.getRegister(regcounter+1)))
           print (f" Struct: %d" % value)
           values[lregs[i][0]]=int(''.join(map(str, value)))#/(10**lregs[i][3])
           if i<len(lregs)-1:
               increment = lregs[i+1][1]-lregs[i][1]
               #print ("calculated increment: " + str(increment))
           else:
               increment=2
               #print ("static increment: " + str(increment))
           regcounter+=increment
           i=i+1
        print (values)
    except Exception as e:
        #print(e)
        print ("Exception occured.Waiting 2 sec to reset in read_doublke_bulk: %s" , e)
        client.close()
        time.sleep(2)
        #client.open()


        #print ("i: " +str(i) + "; " + "index: "+ str(increment) +"; " +str(resp.getRegister(increment)/(10**lregs[increment][3])))
        #values[lregs[i][0]]=resp.getRegister(i)/(10**lregs[i][3])
     #index = 0
     #for reg in lregs:
     #   values[reg[0]]=resp.getRegister(index + lregs[len(lregs)-1][1]-lregs[index][1])/reg[3]
     #   index += 1
     #print ("Myvalues" +str(values))

def read_bulk (client, lregs ):
    bulklen=lregs[len(lregs)-1][1]-lregs[0][1]+1
    #print ("Bulklen: " +str(bulklen))
    try:
        resp = client.read_holding_registers(lregs[0][1],count=bulklen, slave=24)
        if (resp.function_code >= int('0x80',16)):
           print ("Received error code %",resp.function_code)
           return
        print(str(resp.registers))
     
        global values 
        i=0
        regcounter=0
        increment=0
        
        while i < len(lregs):
           #print ("i: " + str(i) + " regcounter: " +str(regcounter) + " getRegister: " + str(resp.getRegister(regcounter)))
           values[lregs[i][0]]=resp.getRegister(regcounter)/(10**lregs[i][3])
           if i<len(lregs)-1: 
               increment = lregs[i+1][1]-lregs[i][1]
               #print ("calculated increment: " + str(increment))
           else: 
               increment=1
               #print ("static increment: " + str(increment))
           regcounter+=increment   
           i=i+1
        
    except Exception as e:
        print ("Exception occured.Waiting 2 sec to reset in read_bulk: %s" ,e)
        client.close()
        time.sleep(2)
        #client.open()
        

def read_sdm530 (client ):
    meter = sdm_modbus.SDM630(
        device='/dev/ttyUSB0',
        stopbits=1,
        parity='N',
        baud=9600,
        timeout=1,
        unit=4
    )
   # print("\nInput Registers:")
   # print(f"{meter}:")
    lst = ['l1_power_active','l2_power_active','l3_power_active','total_power_active','import_energy_active']
    global values 
    for k, v in meter.read_all(sdm_modbus.registerType.INPUT).items():
        address, length, rtype, dtype, vtype, label, fmt, batch, sf = meter.registers[k]
        if ( any(k in x for x in lst) ):
           values['sdm530_'+k]=v
    #    if type(fmt) is list or type(fmt) is dict:
    #        print(f"\t{label}: {fmt[str(v)]}")
    #    elif vtype is float:
    #        print(f"\t{label}: {v:.2f}{fmt}")
    #    else:
    #        print(f"\t{label}: {v}{fmt}")

def read_sensor (client, lregs ):
    bulklen=lregs[len(lregs)-1][1]-lregs[0][1]+1
    #print ("Bulklen: " +str(bulklen))
    global values 
    try:
        resp = client.read_holding_registers(lregs[0][1],count=bulklen, slave=1)
        if (resp.function_code >= int('0x80',16)):
           print ("Received error code %",resp.function_code)
           return
        print(str(resp.registers))
     
        
        i=0
        regcounter=0
        increment=0
        
        while i < len(lregs):
           #print ("i: " + str(i) + " regcounter: " +str(regcounter) + " getRegister: " + str(resp.getRegister(regcounter)))
           values[lregs[i][0]]=resp.getRegister(regcounter)/(10**lregs[i][3])
           if i<len(lregs)-1: 
               increment = lregs[i+1][1]-lregs[i][1]
               #print ("calculated increment: " + str(increment))
           else: 
               increment=1
               #print ("static increment: " + str(increment))
           regcounter+=increment   
           i=i+1
        logger.debug ("sensor")
        #logger.debug (values)
    except:
        print ("Exception occured accessing sensor.Waiting 3 sec to stabilize")
        values['c1'] = 0
        time.sleep(3)





   


        








         
@app.route('/test/')
def test():
    loop()
    return 'rest'
#@app.route('/test1/')
def test1():
    loop()
    1/0
    return 'rest'
#@app.errorhandler(500)
def handle_500(error):
    return str(error), 500          
    
# Using the special variable 
# __name__
if __name__=="__main__":
    print("")
    app.run(host="0.0.0.0", port=6000, debug=True)
    #while (1 ):
    #    loop()
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
   
   

        
  
