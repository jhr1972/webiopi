#!/bin/python3




import datetime
import time
import webiopi
import sys
import struct
import logging
import pymodbus.client.serial
from pysnmp.hlapi import *
from flask import Flask
sys.path.insert(0,"/home/pi/webiopi/macros")
from Basics  import *
from webiopi.utils.types import values


GPIO = webiopi.GPIO
level = "init"
power = "init"
rpm = "init"
deltaForAction = 1
lastAction = None
impulsdauer = 3
impulsstart = 0
l_result = []

aktuellerSollwert = 35
aktuellesZeitfenster = 1800
automationActive = "on"

regs = [
   ( 'Va'     ,0x61, '%6.1f',1 ), # Voltage Phase A [V]
   ( 'Vb'     ,0x62, '%6.1f',1 ), # Voltage Phase B [V]
   ( 'Vc'     ,0x63, '%6.1f',1 ), # Voltage Phase C [V]
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
         ( 'Pa_compl'     ,0x164, '%6.1f',1 ), # Active Power with complement
         ( 'Pb_compl'     ,0x166, '%6.1f',1 ), # Active Power with complement
         ( 'Pc_compl'     ,0x168, '%6.1f',1 ), # Active Power with complement
         ( 'P_compl'     ,0x16A, '%6.1f',1 ), # Active Total Power with complement
]
cl = pymodbus.client.ModbusSerialClient( port='/dev/ttyUSB1', baudrate=9600, parity='N',stopbits=1, timeout=1)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = False
# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
fh = logging.FileHandler(r'/var/log/turbine.log')

# create formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

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
    if ( "on" in automationActive.lower() ):
        automation()
    else:
        logger.debug("skipping automation")
    
    read_bulk(cl,regs)
    read_double_bulk(cl,double_regs)
    webiopi.sleep(1)


def read_double_bulk (client, lregs ):
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
        print(e)
        print ("Exception occured.Waiting 3 sec to stabilize")
        time.sleep(3)



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
        print (values)
    except:
        print ("Exception occured.Waiting 3 sec to stabilize")
        time.sleep(3)

def automation():
    logger.debug("Executing automation")
    global lastAction
    if (lastAction is None):
        lastAction=int(time.time()-aktuellesZeitfenster)
        logger.debug("Initial setting of lastAction: %s", lastAction )

    if (time.time() - lastAction > aktuellesZeitfenster ):
        delta=int(level)-aktuellerSollwert
        if (abs(delta) >=  deltaForAction and delta > 0 and waterlevel.isStable() ):
          logger.info("Klappe muss hoch %d", int(level)-aktuellerSollwert )
          klappeBewegen("up")
        elif (abs(delta) >=  deltaForAction and delta < 0 and waterlevel.isStable() and powerlevel.getAverageValues() >= 999):
          logger.info("Klappe muss runter %d", int(level)-aktuellerSollwert)
          klappeBewegen("down")
        elif (abs(delta) >=  deltaForAction and delta < 0 and waterlevel.isStable() and powerlevel.getAverageValues() < 999):
          logger.info("Klappe müsste runter, aber average Power %d unter Minumum %d" ,powerlevel.getAverageValues(), 999)
          
        else:
          logger.debug("Keine Klappenbewegung notwendig")
    
    else:
        logger.info("No Action due to latency. Next check in %d  seconds",int( aktuellesZeitfenster -(time.time() - lastAction)))

def klappeBewegen(direction):
    global impulsstart
    global lastAction
    if (impulsstart == 0 ):
        impulsstart = int(time.time())
    if (int(time.time()) - impulsstart < impulsdauer ):
        if ( "up" in direction):
            logger.debug("GPIO19 (kleine Klappe auf) aktive")
            GPIO.output(19, True)
        elif ( "down" in direction):
            logger.debug("GPIO26 (kleine Klappe zu) aktive")
            GPIO.output(26, True)
        else:
             logger.error("Direction undefined")
    else:
         logger.info ("GPIO19 (kleine Klappe auf) inaktive")
         logger.info ("GPIO26 (kleine Klappe zu)  inaktive")
         GPIO.output(19, False)
         GPIO.output(26, False)
         impulsstart = 0
         lastAction = int(time.time())
         
         

@webiopi.macro
def getLevel():
    #print("getLevel called")
    return level
    
@webiopi.macro
def getPower():
    #print("getPower called")
    return power

@webiopi.macro
def getRpm():
    #print("getRpm called")
    return rpm

@webiopi.macro
def setAutomationActive(lAutomationActive ):
    print("setAutomationActive called:" ,lAutomationActive)
    global automationActive 
    if ("On" in lAutomationActive ):
        automationActive = "On"    
    if ("Off" in lAutomationActive ):
        automationActive = "Off"

@webiopi.macro
def setValues(l_aktuellerSollwert,l_aktuellesZeitfenster ):
    print("setValues called:" , l_aktuellerSollwert,l_aktuellesZeitfenster)
    global aktuellerSollwert 
    global aktuellesZeitfenster 
    aktuellerSollwert=int(l_aktuellerSollwert)
    aktuellesZeitfenster=int(l_aktuellesZeitfenster)


   

@webiopi.macro
def getValues():
    #print("getValues called")
    if values.get('Ca') and values.get('Pa_compl'):
      return "%s;%d;%d;%.2f;%.2f;%.2f;%d;%.2f;%d;%d;%d;%d;%d" % (automationActive, aktuellerSollwert, aktuellesZeitfenster, values['Ca'], values['Cb'], values['Cc'], values['P_active'], values['Freq'],  values['Pa_compl'],  values['Pb_compl'],  values['Pc_compl'],  values['P_compl'], int( aktuellesZeitfenster -(time.time() - lastAction)))
    else:
      return "%s;%d;%d;%.2f;%.2f;%.2f;%.3f;%.2f,%d,%d,%d,%d" % (automationActive, aktuellerSollwert, aktuellesZeitfenster, 0,0,0,0,0,0,0,0,0 ) 
    #return "%s;%d;%d" % (automationActive, aktuellerSollwert, aktuellesZeitfenster)


@webiopi.macro
def getAllSmtp():
    #logger.debug("getAllSmtp called")
    mystring = ''
    for x in l_result:
        x.replace(" ", "")
        mystring += x+';'
    #logger.debug(f"getAllSmtp: {mystring}")
    return mystring


@webiopi.macro
def setAutomationActive(l_automationActive):
    print("setAutomationActive called: ", l_automationActive)
    global automationActive 
    automationActive=l_automationActive
    

@webiopi.macro
def getAutomationActive():
    print("getAutomationActive called")
    return automationActive

         
#@app.route('/test/')
def test():
    return 'rest'
#@app.route('/test1/')
def test1():
    1/0
    return 'rest'
#@app.errorhandler(500)
def handle_500(error):
    return str(error), 500 
    
# Using the special variable 
# __name__
if __name__=="__main__":
    print("")
    #app.run()
    #loop()
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
   

        
  
