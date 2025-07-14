#!/usr/bin/python3

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
from flask import Flask # Flask might not be needed if WebIOPi handles all HTTP requests
sys.path.insert(0,"/home/pi/webiopi/macros")
from Basics  import * # Assuming this contains your Level class
from webiopi.utils.types import values # Access to WebIOPi's global values dictionary
from pymodbus.register_read_message import ReadInputRegistersResponse
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

GPIO = webiopi.GPIO
level = "init"
power = "init"
rpm = "init"
deltaForAction = 1
lastAction = None # Renamed to last_automation_action_time for clarity in "On" mode
impulsdauer = 3
impulsstart = 0

# Global variables for automation mode
aktuellerSollwert = 40
aktuellesZeitfenster = 1800 # Time window for "On" mode automation checks
automationActive = "Off" # Initial state should be "Off" by default

# Batch Mode Specific Variables ---
batch_state = "WAITING" # "WAITING" or "RUNNING"
batch_operation_start_time = None
batch_next_state_change_time = None # When the next state transition is scheduled

# Batch configuration parameters 
WATER_LEVEL_HIGH_THRESHOLD =41.0 #  Water level (percentage or actual units) to start running
WATER_LEVEL_LOW_THRESHOLD = 35.0  #  Water level to stop running
MAX_BATCH_RUN_DURATION_SECONDS = 4 * 3600 # Max run duration in seconds (4 hours)
MIN_BATCH_WAIT_DURATION_SECONDS = 6 * 3600 #  Min wait duration in seconds (6 hours)



# global app = Flask(__name__) # This line will cause an error if uncommented here
l_result = []

# SDM Modbus Register Definitions (as in your original code)
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

# Logger setup (as in your original code)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = False
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
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
ch.setFormatter(formatter)
fh.setFormatter(formatter)
logger.addHandler(ch)
logger.addHandler(fh)

# Assuming Level class is in Basics.py as you indicated
waterlevel = Level(300,"level",logger) # maxAge
powerlevel = Level(100,"power",logger) # maxAge


# --- Helper Function for Flap Control ---
# This function will encapsulate the actual GPIO operations for flap control.
# This is a critical function; ensure your GPIO pins are correct and safe.
def control_flaps(action):
    """
    Controls the turbine flaps.
    'action' can be 'open_full', 'close_full', 'open_increment', 'close_increment', 'stop'.
    """
    if action == "open_full":
        logger.info("Opening flaps to full (GPIO %d active)", 19)
        # Assuming 19 opens "kleine Klappe" fully
        # You might need to add logic for "grosse Klappe" too if "full" means both
        GPIO.output(19, True) # Activate open
        GPIO.output(26, False) # Deactivate close
        # Add a delay or sensor feedback to ensure it fully opens, then turn off GPIO
        # For simplicity, we'll assume it's momentary or handled by subsequent calls
        # For continuous "open_full" you might need a different approach
        time.sleep(impulsdauer) # Keep active for impulsdauer
        GPIO.output(19, False) # Deactivate open
        logger.info("Flaps open command sent.")

    elif action == "close_full":
        logger.info("Closing flaps to full (GPIO %d active)", 26)
        # Assuming 26 closes "kleine Klappe" fully
        GPIO.output(26, True) # Activate close
        GPIO.output(19, False) # Deactivate open
        time.sleep(impulsdauer) # Keep active for impulsdauer
        GPIO.output(26, False) # Deactivate close
        logger.info("Flaps close command sent.")

    elif action == "open_increment":
        logger.debug("Incrementally opening small flap (GPIO %d active)", 19)
        # Implement logic for incremental opening, potentially using impulsstart/impulsdauer
        # and checking current flap position if available.
        klappeBewegen("up") # Re-use your existing incremental function
    
    elif action == "close_increment":
        logger.debug("Incrementally closing small flap (GPIO %d active)", 26)
        # Implement logic for incremental closing
        klappeBewegen("down") # Re-use your existing incremental function

    elif action == "stop":
        logger.info("Stopping all flap movements.")
        GPIO.output(19, False)
        GPIO.output(26, False)
        GPIO.output(16, False) # Assuming these are for gross
        GPIO.output(20, False)
        global impulsstart
        impulsstart = 0 # Reset impulse timer if it was used

    # You might also want to add control for the "Gross-Klappe" (GPIO 16, 20) here
    # depending on how "full open/close" translates to your specific setup.


# --- Main WebIOPi Loop ---
def loop():
    global l_result, automationActive, batch_state, batch_operation_start_time, batch_next_state_change_time
    
    # Initialize l_result if empty
    if not l_result:
        l_result = [""] * 100 # Pre-fill with empty strings

    # Fetch SNMP values
    g = bulkCmd(
        SnmpEngine(),
        CommunityData('public'),
        UdpTransportTarget(('192.168.100.177', 161)),
        ContextData(),
        0, 100,
        ObjectType(ObjectIdentity('1.3.6.1.4.1.13576.10.1.100.1.1.3.0'))
    )
    
    for i in range(100):
        try:
            result = next(g)
            l_result[i] = str(result[3][0]).split('=')[1]
            
            if i == 71:
                global rpm
                rpm = l_result[i]
                values["turbine_rpm"] = rpm
            elif i == 72:
                global level
                level = l_result[i]
                values["turbine_level"] = level
            elif i == 73:
                global power
                power = l_result[i]
                powerlevel.addLevel(int(power))
                values["turbine_currentpower"] = power
                values["turbine_averagepower"] = str(round(powerlevel.getAverageValues()))
        except StopIteration:
            logger.warning("SNMP bulkCmd finished prematurely.")
            break
        except Exception as e:
            logger.error(f"Error fetching SNMP OID {i}: {e}")
            break # Exit loop if a significant error occurs

    # Update water level for stability check
    waterlevel.addLevel(level)

    # --- Automation Logic based on automationActive mode ---
    current_time = datetime.datetime.now()

    if automationActive == "On":
        automation() # Your existing continuous automation logic
        logger.debug("Automation mode: On")

    elif automationActive == "Batch":
        logger.debug(f"Automation mode: Batch. Current state: {batch_state}")
        current_water_level_val = float(level) # Assuming 'level' from SNMP is numeric

        if batch_state == "WAITING":
            # Check if enough time has passed since last run/transition AND water level is high
            if (batch_next_state_change_time is None or current_time >= batch_next_state_change_time) \
               and current_water_level_val >= WATER_LEVEL_HIGH_THRESHOLD:
                logger.info("BATCH: Water level (%.2f) >= HIGH threshold (%.2f) and wait time passed. Starting RUNNING state.",
                            current_water_level_val, WATER_LEVEL_HIGH_THRESHOLD)
                
                control_flaps("open_full") # Open flaps fully
                batch_state = "RUNNING"
                batch_operation_start_time = current_time
                batch_next_state_change_time = current_time + datetime.timedelta(seconds=MAX_BATCH_RUN_DURATION_SECONDS)
                logger.info(f"BATCH: Next state change (stop) scheduled for: {batch_next_state_change_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                logger.debug(f"BATCH: WAITING. Water level: {current_water_level_val}. Next start: {batch_next_state_change_time if batch_next_state_change_time else 'N/A'}")

        elif batch_state == "RUNNING":
            # Check if water level is too low OR max run duration is reached
            if current_water_level_val <= WATER_LEVEL_LOW_THRESHOLD:
                logger.info("BATCH: Water level (%.2f) <= LOW threshold (%.2f). Stopping RUNNING state.",
                            current_water_level_val, WATER_LEVEL_LOW_THRESHOLD)
                control_flaps("close_full") # Close flaps fully
                batch_state = "WAITING"
                batch_operation_start_time = None # Reset for next cycle
                batch_next_state_change_time = current_time + datetime.timedelta(seconds=MIN_BATCH_WAIT_DURATION_SECONDS)
                logger.info(f"BATCH: Next state change (start after wait) scheduled for: {batch_next_state_change_time.strftime('%Y-%m-%d %H:%M:%S')}")
            elif current_time >= batch_next_state_change_time:
                logger.info("BATCH: Max run duration reached. Stopping RUNNING state.")
                control_flaps("close_full") # Close flaps fully
                batch_state = "WAITING"
                batch_operation_start_time = None # Reset for next cycle
                batch_next_state_change_time = current_time + datetime.timedelta(seconds=MIN_BATCH_WAIT_DURATION_SECONDS)
                logger.info(f"BATCH: Next state change (start after wait) scheduled for: {batch_next_state_change_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                remaining_run_time = batch_next_state_change_time - current_time
                logger.debug(f"BATCH: RUNNING. Water level: {current_water_level_val}. Time remaining: {remaining_run_time}")

    else: # automationActive == "Off"
        logger.debug("Automation mode: Off. Skipping automation.")
        control_flaps("stop") # Ensure flaps are stopped when off

    # Read SDM meters
    read_sdm530()
    read_sdm630() # Ensure this is always called to update values for frontend
    
    webiopi.sleep(0.5)


def read_sdm630 ( ):
    # Your existing sdm630 reading logic
    meter = sdm_modbus.SDM630(
        device='/dev/ttyUSB1',
        stopbits=1,
        parity='N',
        baud=9600,
        timeout=1,
        unit=1
    )
    lst = ['l1_voltage','l2_voltage','l3_voltage','l1_power_active','l2_power_active','l3_power_active','total_power_active','import_energy_active','export_energy_reactive','frequency']
    global values 
    try:
        for k, v in meter.read_all(sdm_modbus.registerType.INPUT).items():
            address, length, rtype, dtype, vtype, label, fmt, batch, sf = meter.registers[k]
            if any(k in x for x in lst):
               values['sdm630_'+k]=v
    except Exception as e:
        logger.error(f"Error reading SDM630: {e}")
        # Optionally set default/error values in 'values' if reading fails


def read_sdm530 ( ):
    # Your existing sdm530 reading logic
    meter = sdm_modbus.SDM630(
        device='/dev/ttyUSB0',
        stopbits=1,
        parity='N',
        baud=9600,
        timeout=1,
        unit=4
    )
    lst = ['l1_power_active','l2_power_active','l3_power_active','total_power_active','import_energy_active']
    global values 
    try:
        for k, v in meter.read_all(sdm_modbus.registerType.INPUT).items():
            address, length, rtype, dtype, vtype, label, fmt, batch, sf = meter.registers[k]
            if any(k in x for x in lst):
               values['sdm530_'+k]=v
    except Exception as e:
        logger.error(f"Error reading SDM530: {e}")
        # Optionally set default/error values in 'values' if reading fails

def automation():
    """
    Your existing continuous automation logic for "On" mode.
    This function controls flaps based on water level and power output to maintain a setpoint.
    """
    global last_automation_action_time # Using the clearer name
    if (last_automation_action_time is None):
        last_automation_action_time = int(time.time() - aktuellesZeitfenster)
        logger.debug("Initial setting of last_automation_action_time: %s", last_automation_action_time)

    if (time.time() - last_automation_action_time > aktuellesZeitfenster):
        # Ensure 'level' is numeric for comparison
        current_level_val = float(level) 
        delta = current_level_val - aktuellerSollwert
        
        # Power threshold for closing flaps (to avoid running dry)
        MIN_POWER_FOR_OPERATION = 999 

        if (abs(delta) >= deltaForAction and delta > 0 and waterlevel.isStable()):
            logger.info("Klappe muss hoch (level: %.2f, soll: %d, delta: %.2f)", current_level_val, aktuellerSollwert, delta)
            control_flaps("open_increment") # Use the unified control_flaps
        elif (abs(delta) >= deltaForAction and delta < 0 and waterlevel.isStable() and powerlevel.getAverageValues() >= MIN_POWER_FOR_OPERATION):
            logger.info("Klappe muss runter (level: %.2f, soll: %d, delta: %.2f)", current_level_val, aktuellerSollwert, delta)
            control_flaps("close_increment") # Use the unified control_flaps
        elif (abs(delta) >= deltaForAction and delta < 0 and waterlevel.isStable() and powerlevel.getAverageValues() < MIN_POWER_FOR_OPERATION):
            logger.info("Klappe müsste runter, aber average Power %d unter Minimum %d", powerlevel.getAverageValues(), MIN_POWER_FOR_OPERATION)
            # Potentially close flaps more aggressively or halt operations if power is too low
            control_flaps("stop") # Or close incrementally to prevent damage
        else:
            logger.debug("Keine Klappenbewegung notwendig. Delta: %.2f, Water Stable: %s", delta, waterlevel.isStable())
            control_flaps("stop") # Ensure flaps stop moving if no action is needed
        
        last_automation_action_time = int(time.time()) # Update last action time

    else:
        time_until_next_check = int(aktuellesZeitfenster - (time.time() - last_automation_action_time))
        logger.info("No Action due to latency. Next check in %d seconds", time_until_next_check)
        control_flaps("stop") # Stop flaps if in latency period


def klappeBewegen(direction):
    """
    Handles incremental flap movement for a defined impulse duration.
    This function is primarily for the "On" automation mode.
    """
    global impulsstart
    # No direct global lastAction update here, it's done in `automation()`
    
    if impulsstart == 0:
        impulsstart = int(time.time())
        logger.debug(f"Starting impulse for direction: {direction}")
    
    if int(time.time()) - impulsstart < impulsdauer:
        if direction == "up":
            GPIO.output(19, True)  # Kleine Klappe auf
            GPIO.output(26, False)
        elif direction == "down":
            GPIO.output(26, True)  # Kleine Klappe zu
            GPIO.output(19, False)
        else:
            logger.error("klappeBewegen: Direction undefined or invalid: %s", direction)
            control_flaps("stop") # Stop to prevent unexpected behavior
    else:
        logger.debug(f"Impulse duration ({impulsdauer}s) for {direction} finished. Stopping flap movement.")
        GPIO.output(19, False)
        GPIO.output(26, False)
        impulsstart = 0 # Reset for the next impulse


@webiopi.macro
def getLevel():
    return level
    
@webiopi.macro
def getPower():
    return power

@webiopi.macro
def getRpm():
    return rpm

@webiopi.macro
def setAutomationActive(l_automationActive):
    """
    Sets the automation mode for the turbine.
    Possible values: "On", "Off", "Batch".
    """
    global automationActive, batch_state, batch_operation_start_time, batch_next_state_change_time
    logger.info(f"setAutomationActive called with status: {l_automationActive}")

    # Set new mode
    automationActive = l_automationActive

    # Reset batch specific variables if not entering batch mode
    if automationActive != "Batch":
        batch_state = "WAITING"
        batch_operation_start_time = None
        batch_next_state_change_time = None # Clear any scheduled times
        control_flaps("close_full") # Ensure flaps are closed when switching out of Batch/On
        logger.info(f"Automation set to {automationActive}. Flaps commanded to close.")
    elif automationActive == "Batch":
        # When entering Batch mode, ensure initial state is WAITING and flaps are closed
        batch_state = "WAITING"
        batch_operation_start_time = None
        batch_next_state_change_time = datetime.datetime.now() # Allow immediate check for starting if conditions met
        control_flaps("close_full") # Ensure flaps are closed before starting batch cycle
        logger.info(f"Automation set to Batch. Initializing to WAITING state.")

    # Stop any ongoing flap movements immediately when changing mode
    control_flaps("stop")

@webiopi.macro
def setValues(l_aktuellerSollwert,l_aktuellesZeitfenster ):
    """
    Sets the target setpoint and time window for 'On' automation mode.
    These values are only relevant when automationActive is "On".
    """
    global aktuellerSollwert, aktuellesZeitfenster
    aktuellerSollwert = int(l_aktuellerSollwert)
    aktuellesZeitfenster = int(l_aktuellesZeitfenster)
    logger.info(f"setValues called. Sollwert: {aktuellerSollwert}, Zeitfenster: {aktuellesZeitfenster}")


@webiopi.macro
def getValues():
    """
    Returns current system values to the frontend.
    The string format must match what the HTML frontend expects.
    """
    global automationActive, aktuellerSollwert, aktuellesZeitfenster, batch_state, batch_next_state_change_time, last_automation_action_time
    
    # Calculate countdown/status based on automation mode
    countdown_str = "N/A"
    if automationActive == "On":
        if last_automation_action_time:
            time_until_next_check = max(0, int(aktuellesZeitfenster - (time.time() - last_automation_action_time)))
            countdown_str = str(time_until_next_check) + "s"
        else:
            countdown_str = "Init"
    elif automationActive == "Batch":
        current_time = datetime.datetime.now()
        if batch_state == "WAITING":
            if batch_next_state_change_time and batch_next_state_change_time > current_time:
                time_left_seconds = int((batch_next_state_change_time - current_time).total_seconds())
                countdown_str = f"Wait: {str(datetime.timedelta(seconds=time_left_seconds)).split('.')[0]}"
            else:
                countdown_str = "Waiting for Water"
        elif batch_state == "RUNNING":
            if batch_next_state_change_time and batch_next_state_change_time > current_time:
                time_left_seconds = int((batch_next_state_change_time - current_time).total_seconds())
                countdown_str = f"Run: {str(datetime.timedelta(seconds=time_left_seconds)).split('.')[0]}"
            else:
                countdown_str = "Running (No End)" # Should not happen if MAX_BATCH_RUN_DURATION_SECONDS is set
    
    # Ensure all values exist in 'values' dictionary to prevent KeyError
    # Provide default 0 or "" if not found (e.g., if SDM reader failed)
    current_val = values.get('current', 0.0) # Placeholder for current sensor
    if isinstance(current_val, (int, float)):
        formatted_current = f"{current_val:.2f}"
    else:
        formatted_current = str(current_val)

    return "%s;%d;%d;%.2f;%.2f;%.2f;%d;%.2f;%d;%d;%d;%d;%s;%s;%d;%d;%d;%d;%.2f" % (
        automationActive,
        aktuellerSollwert,
        aktuellesZeitfenster,
        values.get('sdm630_l1_voltage', 1.0), # Voltage Phase A
        values.get('sdm630_l2_voltage', 2.0), # Voltage Phase B
        values.get('sdm630_l3_voltage', 3.0), # Voltage Phase C
        values.get('sdm630_total_power_active', 0), # Total Power from SDM630
        values.get('sdm630_frequency', 0.0), # Frequency from SDM630
        values.get('sdm630_l1_power_active', 0), # L1 Power from SDM630
        values.get('sdm630_l2_power_active', 0), # L2 Power from SDM630
        values.get('sdm630_l3_power_active', 0), # L3 Power from SDM630
        values.get('sdm630_total_power_active', 0), # Total Power from SDM630
        countdown_str, # Dynamic countdown/status for batch/on mode
        formatted_current, # General current sensor (from your original code)
        values.get('sdm530_l1_power_active', 0), # L1 Power from SDM530
        values.get('sdm530_l2_power_active', 0), # L2 Power from SDM530
        values.get('sdm530_l3_power_active', 0), # L3 Power from SDM530
        values.get('sdm530_total_power_active', 0), # Total Power from SDM530
        values.get('sdm530_import_energy_active', 0.0) # Imported Energy from SDM530
    )
        
@webiopi.macro
def getAllSmtp():
    mystring = ''
    for x in l_result:
        # x.replace(" ", "") # This might not be necessary if split('=')[1] already cleans spaces
        mystring += x + ';'
    return mystring

@webiopi.macro
def getAutomationActive():
    return automationActive

# --- WebIOPi Setup and Teardown ---
def setup():
    # Configure GPIO pins. These should be outputs to control relays for the flaps.
    GPIO.setFunction(19, GPIO.OUT) # Klein-Auf
    GPIO.setFunction(26, GPIO.OUT) # Klein-Zu
    GPIO.setFunction(16, GPIO.OUT) # Gross-Auf
    GPIO.setFunction(20, GPIO.OUT) # Gross-Zu
    GPIO.setFunction(21, GPIO.OUT) # Reset

    # Ensure all flap control pins are OFF initially to prevent unintended movements
    GPIO.output(19, GPIO.LOW)
    GPIO.output(26, GPIO.LOW)
    GPIO.output(16, GPIO.LOW)
    GPIO.output(20, GPIO.LOW)
    GPIO.output(21, GPIO.LOW) # Assuming reset is pulsed later

    # Initialize last_automation_action_time for the "On" mode
    global last_automation_action_time
    last_automation_action_time = time.time() - aktuellesZeitfenster # Set it to trigger immediately at start

    logger.info("WebIOPi setup complete. GPIOs initialized.")

def destroy():
    # Clean up GPIOs when WebIOPi stops
    GPIO.output(19, GPIO.LOW)
    GPIO.output(26, GPIO.LOW)
    GPIO.output(16, GPIO.LOW)
    GPIO.output(20, GPIO.LOW)
    GPIO.output(21, GPIO.LOW)
    GPIO.cleanup()
    logger.info("WebIOPi destroy complete. GPIOs cleaned up.")

# Flask app part (if you're using Flask in parallel to WebIOPi, which is unusual)
# If WebIOPi is serving the macros, you typically don't need a separate Flask app for the same purpose.
# If you are using Flask for other REST endpoints, keep it, otherwise you can remove it.
# If you keep it, make sure it doesn't block WebIOPi's loop or port.
# The `app.run()` line will typically block, so it's not ideal inside `if __name__ == "__main__":`
# for a WebIOPi script. WebIOPi itself manages the main loop.

# @app.route('/test/')
# def test():
#     return 'rest'

# @app.route('/test1/')
# def test1():
#     1/0
#     return 'rest'

# @app.errorhandler(500)
# def handle_500(error):
#     return str(error), 500          
    
if __name__=="__main__":
    # This block is usually for testing the script outside of WebIOPi.
    # WebIOPi directly calls setup(), loop(), and destroy().
    print("This script is designed to run with WebIOPi. Running it directly might not behave as expected.")
    print("If you intend to run a Flask app, ensure it's not conflicting with WebIOPi's port.")
    
    # If you must run Flask from here, you would typically use a separate thread or process.
    # Or, the WebIOPi server itself could be configured to host Flask.
    # Example (not recommended for simple WebIOPi macro scripts due to complexity):
    # import multiprocessing
    # def run_flask():
    #     app = Flask(__name__)
    #     app.run(port=5000) # Use a different port than WebIOPi (default 8000)
    #
    # flask_process = multiprocessing.Process(target=run_flask)
    # flask_process.start()
    
    # For WebIOPi, you just need this script in your WebIOPi macros folder.
    # The `loop()` function will be called repeatedly by WebIOPi.
    # `setup()` and `destroy()` are also called by WebIOPi.
    
    # If running directly for quick testing (without WebIOPi environment):
    # setup()
    # while True:
    #     loop()
    
    # Removed the problematic app.run() here as it conflicts with WebIOPi's main loop.
    pass