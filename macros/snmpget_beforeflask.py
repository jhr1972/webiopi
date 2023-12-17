#!/bin/python3




import datetime
import time
import webiopi
import sys
import logging
from pysnmp.hlapi import *
from flask import Flask
sys.path.insert(0,"/home/pi/webiopi/macros")
from Basics  import *

GPIO = webiopi.GPIO
level = "init"
power = "init"
rpm = "init"
deltaForAction = 1
lastAction = None
impulsdauer = 3
impulsstart = 0
l_result = []

aktuellerSollwert = 46
aktuellesZeitfenster = 600
automationActive = "on"

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
      if ( i == 72):
          global level 
          level = str(result[3][0]).split('=')[1]
          #print("Level:", level)
      if ( i == 73):
          global power
          power = str(result[3][0]).split('=')[1]
          powerlevel.addLevel (int(power))
          
          #print("Power:", power)
      i = i+1
    global waterlevel
    waterlevel.addLevel(level)
    if ( "on" in automationActive.lower() ):
        automation()
    else:
        logger.debug("skipping automation")
    
    webiopi.sleep(1)

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
        elif (abs(delta) >=  deltaForAction and delta < 0 and waterlevel.isStable() and powerlevel.getAverageValues() >= 900):
          logger.info("Klappe muss runter %d", int(level)-aktuellerSollwert)
          klappeBewegen("down")
        elif (abs(delta) >=  deltaForAction and delta < 0 and waterlevel.isStable() and powerlevel.getAverageValues() < 900):
          logger.info("Klappe müsste runter, aber average Power %d unter Minumum %d" ,powerlevel.getAverageValues(), 900)
          
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
    return "%s;%d;%d" % (automationActive, aktuellerSollwert, aktuellesZeitfenster)

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
    print("setAutomationActive called")
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
   

        
  