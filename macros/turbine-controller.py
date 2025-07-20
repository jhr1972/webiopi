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
from flask import Flask 
sys.path.insert(0,"/home/pi/webiopi/macros")
from Basics  import * # Make sure Basics.py exists and works if you use it for Level
from webiopi.utils.types import values # Assuming 'values' is defined and used correctly
from pymodbus.register_read_message import ReadInputRegistersResponse
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

GPIO = webiopi.GPIO
level = "init"
power = "init"
rpm = "init"
deltaForAction = 1
last_automation_action_time = None 
impulsdauer = 3
impulsstart = 0

# Global variables for automation mode
aktuellerSollwert = 40
aktuellesZeitfenster = 1800 
automationActive = "Off" # Initial state should be "Off"

# --- Batch Mode Specific Variables ---
batch_state = "WAITING" 
batch_operation_start_time = None
batch_next_state_change_time = None 

# Batch configuration parameters (ADJUST THESE VALUES FOR YOUR PLANT)
WATER_LEVEL_HIGH_THRESHOLD = 41.0 
WATER_LEVEL_LOW_THRESHOLD = 35.0  
MAX_BATCH_RUN_DURATION_SECONDS = 4 * 3600 
MIN_BATCH_WAIT_DURATION_SECONDS = 6 * 3600 

l_result = []

# --- NEW: Global variables for reset logic ---
RESET_GPIO = 21 # GPIO pin for the reset button
turbine_reset_in_progress = False # Flag to prevent multiple resets simultaneously

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

# Assuming Level class is correctly imported from Basics
waterlevel = Level(300,"level",logger) 
powerlevel = Level(100,"power",logger) 


# --- Helper Function for Flap Control ---
def control_flaps(action):
    """
    Controls the turbine flaps.
    'action' can be 'open_full', 'close_full', 'open_increment', 'close_increment', 'stop'.
    'stop' explicitly sets pins LOW.
    """
    global impulsstart
    
    KLEIN_AUF = 19
    KLEIN_ZU = 26
    GROSS_AUF = 16
    GROSS_ZU = 20

    if action == "open_full":
        logger.info("Command: Open flaps to full (GPIO %d)", KLEIN_AUF)
        GPIO.output(KLEIN_AUF, True) # Activate open
        GPIO.output(KLEIN_ZU, False) # Deactivate close
        GPIO.output(GROSS_AUF, True) # Also open large flap fully
        GPIO.output(GROSS_ZU, False)

    elif action == "close_full":
        logger.info("Command: Close flaps to full (GPIO %d)", KLEIN_ZU)
        GPIO.output(KLEIN_ZU, True) # Activate close
        GPIO.output(KLEIN_AUF, False) # Deactivate open
        GPIO.output(GROSS_ZU, True) # Also close large flap fully
        GPIO.output(GROSS_AUF, False)
        
    elif action == "open_increment":
        logger.debug("Command: Incrementally opening small flap")
        klappeBewegen(KLEIN_AUF, KLEIN_ZU) 
    
    elif action == "close_increment":
        logger.debug("Command: Incrementally closing small flap")
        klappeBewegen(KLEIN_ZU, KLEIN_AUF) 

    elif action == "stop":
        logger.info("Command: Stopping all flap movements.")
        # This action explicitly forces all associated pins LOW.
        GPIO.output(KLEIN_AUF, False)
        GPIO.output(KLEIN_ZU, False)
        GPIO.output(GROSS_AUF, False)
        GPIO.output(GROSS_ZU, False)
        
        impulsstart = 0 # Reset impulse timer

# --- NEW: Turbine Reset Function ---
def _perform_reset_pulse():
    """Internal function to perform the actual GPIO pulse. Runs in a separate thread."""
    global turbine_reset_in_progress
    logger.info(f"Initiating turbine reset pulse (GPIO {RESET_GPIO} HIGH for 1s).")
    GPIO.output(RESET_GPIO, GPIO.HIGH)
    time.sleep(1) # This sleep happens in the separate thread, not blocking main loop
    GPIO.output(RESET_GPIO, GPIO.LOW)
    logger.info(f"Turbine reset pulse complete (GPIO {RESET_GPIO} LOW).")
    turbine_reset_in_progress = False # Reset flag after operation is done

def reset_turbine():
    """
    Triggers a non-blocking reset pulse for the turbine.
    Uses a separate thread to avoid blocking the main WebIOPi loop.
    """
    global turbine_reset_in_progress
    if not turbine_reset_in_progress:
        logger.warning("Turbine Alarm detected! Attempting automatic reset sequence.")
        turbine_reset_in_progress = True
        # Start the reset operation in a new daemon thread
        reset_thread = threading.Thread(target=_perform_reset_pulse)
        reset_thread.daemon = True # Allows the main program to exit even if this thread is running
        reset_thread.start()
    else:
        logger.debug("Turbine reset already in progress or recently completed. Skipping additional reset call.")


# --- Main WebIOPi Loop ---
def loop():
    global l_result, automationActive, batch_state, batch_operation_start_time, batch_next_state_change_time
    
    # Read SNMP and SDM meters in every loop iteration
    if not l_result:
        l_result = [""] * 100 

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
            # Ensure l_result[17] is handled if SNMP fails completely
            if i == 17:
                l_result[17] = "0" # Default to no alarm if cannot read
            break 

    waterlevel.addLevel(level)
    read_sdm530()
    read_sdm630() 

    current_time = datetime.datetime.now()

    # --- Automation Logic based on automationActive ---
    if automationActive == "On":
        automation() 
        logger.debug("Automation mode: On")

    elif automationActive == "Batch":
        logger.debug(f"Automation mode: Batch. Current state: {batch_state}")
        try:
            current_water_level_val = float(level) 
            # NEW: Get alarm status from l_result (corresponds to smtps[17] in UI)
            current_alarm_status = int(l_result[17])
        except (ValueError, IndexError) as e:
            logger.error(f"Error getting water level or alarm status (l_result[17]): {e}. Using safe defaults.")
            current_water_level_val = 0.0
            current_alarm_status = 0 # Assume no alarm if cannot read or index out of bounds

        # --- NEW: Check for Alarm/Störung first ---
        if current_alarm_status == 1: # Alarm detected (from smtps[17] / l_result[17])
            logger.error("BATCH: Turbine ALARM/Störung detected! Initiating shutdown and reset sequence.")
            control_flaps("close_full") # Shut down flaps
            control_flaps("stop")       # Ensure motors are off
            reset_turbine()             # Trigger the non-blocking reset pulse

            # Transition to WAITING state and set a cool-down period
            batch_state = "WAITING"
            batch_operation_start_time = None 
            # Schedule next check after MIN_BATCH_WAIT_DURATION_SECONDS to allow reset and system to stabilize
            batch_next_state_change_time = current_time + datetime.timedelta(seconds=MIN_BATCH_WAIT_DURATION_SECONDS)
            logger.info(f"BATCH: Alarm detected. Transitioning to WAITING. Next state change scheduled for: {batch_next_state_change_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Important: Exit this loop iteration to prevent further batch logic from running
            # until the next loop cycle, allowing the reset to take effect.
            return 

        # If no alarm, proceed with normal batch logic (WAITING/RUNNING)
        if batch_state == "WAITING":
            if (batch_next_state_change_time is None or current_time >= batch_next_state_change_time) \
               and current_water_level_val >= WATER_LEVEL_HIGH_THRESHOLD:
                logger.info("BATCH: Water level (%.2f) >= HIGH threshold (%.2f) and wait time passed. Starting RUNNING state.",
                            current_water_level_val, WATER_LEVEL_HIGH_THRESHOLD)
                
                control_flaps("open_full") 
                batch_state = "RUNNING"
                batch_operation_start_time = current_time
                batch_next_state_change_time = current_time + datetime.timedelta(seconds=MAX_BATCH_RUN_DURATION_SECONDS)
                logger.info(f"BATCH: Next state change (stop) scheduled for: {batch_next_state_change_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                logger.debug(f"BATCH: WAITING. Water level: {current_water_level_val}. Next start: {batch_next_state_change_time if batch_next_state_change_time else 'N/A'}")

        elif batch_state == "RUNNING":
            if current_water_level_val <= WATER_LEVEL_LOW_THRESHOLD:
                logger.info("BATCH: Water level (%.2f) <= LOW threshold (%.2f). Stopping RUNNING state.",
                            current_water_level_val, WATER_LEVEL_LOW_THRESHOLD)
                control_flaps("close_full") 
                batch_state = "WAITING"
                batch_operation_start_time = None 
                batch_next_state_change_time = current_time + datetime.timedelta(seconds=MIN_BATCH_WAIT_DURATION_SECONDS)
                logger.info(f"BATCH: Next state change (start after wait) scheduled for: {batch_next_state_change_time.strftime('%Y-%m-%d %H:%M:%S')}")
            elif current_time >= batch_next_state_change_time:
                logger.info("BATCH: Max run duration reached. Stopping RUNNING state.")
                control_flaps("close_full") 
                batch_state = "WAITING"
                batch_operation_start_time = None 
                batch_next_state_change_time = current_time + datetime.timedelta(seconds=MIN_BATCH_WAIT_DURATION_SECONDS)
                logger.info(f"BATCH: Next state change (start after wait) scheduled for: {batch_next_state_change_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                remaining_run_time = batch_next_state_change_time - current_time
                logger.debug(f"BATCH: RUNNING. Water level: {current_water_level_val}. Time remaining: {remaining_run_time}")

    else: # automationActive == "Off"
        logger.debug("Automation mode: Off. Allowing manual GPIO control. No flap actions by script.")
    
    webiopi.sleep(0.5)


def read_sdm630 ( ):
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


def read_sdm530 ( ):
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

def automation():
    """
    Your existing continuous automation logic for "On" mode.
    This function controls flaps based on water level and power output to maintain a setpoint.
    """
    global last_automation_action_time 
    if (last_automation_action_time is None):
        last_automation_action_time = time.time() - aktuellesZeitfenster 
        logger.debug("Initial setting of last_automation_action_time: %s", last_automation_action_time)

    if (time.time() - last_automation_action_time > aktuellesZeitfenster):
        try:
            current_level_val = float(level) 
        except ValueError:
            logger.error(f"Could not convert water level '{level}' to float. Using 0.0 for safety.")
            current_level_val = 0.0

        delta = current_level_val - aktuellerSollwert
        
        MIN_POWER_FOR_OPERATION = 999 

        if (abs(delta) >= deltaForAction and delta > 0 and waterlevel.isStable()):
            logger.info("Klappe muss hoch (level: %.2f, soll: %d, delta: %.2f)", current_level_val, aktuellerSollwert, delta)
            control_flaps("open_increment") 
        elif (abs(delta) >= deltaForAction and delta < 0 and waterlevel.isStable() and powerlevel.getAverageValues() >= MIN_POWER_FOR_OPERATION):
            logger.info("Klappe muss runter (level: %.2f, soll: %d, delta: %.2f)", current_level_val, aktuellerSollwert, delta)
            control_flaps("close_increment") 
        elif (abs(delta) >= deltaForAction and delta < 0 and waterlevel.isStable() and powerlevel.getAverageValues() < MIN_POWER_FOR_OPERATION):
            logger.info("Klappe müsste runter, aber average Power %d unter Minimum %d", powerlevel.getAverageValues(), MIN_POWER_FOR_OPERATION)
            control_flaps("stop") 
        else:
            logger.debug("Keine Klappenbewegung notwendig. Delta: %.2f, Water Stable: %s", delta, waterlevel.isStable())
            control_flaps("stop") 
        
        last_automation_action_time = time.time() 

    else:
        time_until_next_check = int(aktuellesZeitfenster - (time.time() - last_automation_action_time))
        logger.info("No Action due to latency. Next check in %d seconds", time_until_next_check)
        control_flaps("stop") # Still stop if no action is needed within the window

def klappeBewegen(active_pin, inactive_pin):
    """
    Handles incremental flap movement for a defined impulse duration.
    This function is primarily for the "On" automation mode.
    It now accepts the active and inactive pin numbers.
    The goal is to maintain the active_pin HIGH for impulsdauer, then set it LOW.
    """
    global impulsstart
    
    # Only initiate a new impulse if no impulse is currently active, or if it's a new command
    # This prevents re-triggering an impulse if it's already active due to automation
    if impulsstart == 0: # Start a new impulse
        impulsstart = time.time()
        logger.debug(f"Starting impulse for pin {active_pin} (active), {inactive_pin} (inactive)")
        GPIO.output(active_pin, True)
        GPIO.output(inactive_pin, False) 
    
    # Check if the impulse duration is ongoing
    if (time.time() - impulsstart) < impulsdauer:
        pass # Pin stays HIGH
    else:
        logger.debug(f"Impulse duration ({impulsdauer}s) for pin {active_pin} finished. Stopping flap movement.")
        GPIO.output(active_pin, False)
        impulsstart = 0 

    # Ensure the inactive pin is LOW at all times when not actively needed.
    if GPIO.input(inactive_pin) == GPIO.HIGH:
        GPIO.output(inactive_pin, False)
        logger.debug(f"Ensuring inactive pin {inactive_pin} is LOW.")


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
    global automationActive, batch_state, batch_operation_start_time, batch_next_state_change_time
    logger.info(f"setAutomationActive called with status: {l_automationActive}")

    # Set new mode unconditionally
    automationActive = l_automationActive
    logger.debug(f"automationActive set to: {automationActive}") # Log the new state

    # When switching INTO "On" or "Batch" mode, we explicitly ensure a safe start.
    if automationActive in ["On", "Batch"]:
        control_flaps("close_full") # Explicitly close all automation-controlled flaps
        control_flaps("stop") # Ensure all motors are off
        logger.info(f"Automation set to {automationActive}. Flaps explicitly closed and stopped for transition.")
        if automationActive == "Batch":
            batch_state = "WAITING"
            batch_operation_start_time = None
            batch_next_state_change_time = datetime.datetime.now() # Allow immediate check for starting if conditions met
    else: # automationActive == "Off"
        # When switching TO "Off" mode, automation also explicitly stops everything it controls.
        # This brings the system to a safe, non-automated state.
        control_flaps("close_full") # Ensure flaps are closed when automation is off
        control_flaps("stop") # Ensure all motors are off
        batch_state = "WAITING" # Reset batch state
        batch_operation_start_time = None
        batch_next_state_change_time = None # Clear any scheduled times
        logger.info(f"Automation set to Off. Automation-controlled flaps commanded to close and stop. Manual control enabled.")

@webiopi.macro
def setValues(l_aktuellerSollwert,l_aktuellesZeitfenster ):
    global aktuellerSollwert, aktuellesZeitfenster
    aktuellerSollwert = int(l_aktuellerSollwert)
    aktuellesZeitfenster = int(l_aktuellesZeitfenster)
    logger.info(f"setValues called. Sollwert: {aktuellerSollwert}, Zeitfenster: {aktuellesZeitfenster}")


@webiopi.macro
def getValues():
    global automationActive, aktuellerSollwert, aktuellesZeitfenster, batch_state, batch_next_state_change_time, last_automation_action_time
    
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
                countdown_str = "Running (No End)" 
    
    current_val = values.get('current', 0.0) 
    if isinstance(current_val, (int, float)):
        formatted_current = f"{current_val:.2f}"
    else:
        formatted_current = str(current_val)

    # Make sure your Python macro returns the automationActive status as the first element
    # This is critical for the JavaScript logic.
    return "%s;%d;%d;%.2f;%.2f;%.2f;%d;%.2f;%d;%d;%d;%d;%s;%s;%d;%d;%d;%d;%.2f" % (
        automationActive, # This must be the first element
        aktuellerSollwert,
        aktuellesZeitfenster,
        values.get('sdm630_l1_voltage', 0.0), 
        values.get('sdm630_l2_voltage', 0.0), 
        values.get('sdm630_l3_voltage', 0.0), 
        values.get('sdm630_total_power_active', 0), 
        values.get('sdm630_frequency', 0.0), 
        values.get('sdm630_l1_power_active', 0), 
        values.get('sdm630_l2_power_active', 0), 
        values.get('sdm630_l3_power_active', 0), 
        values.get('sdm630_total_power_active', 0), 
        countdown_str, 
        formatted_current, 
        values.get('sdm530_l1_power_active', 0), 
        values.get('sdm530_l2_power_active', 0), 
        values.get('sdm530_l3_power_active', 0), 
        values.get('sdm530_total_power_active', 0), 
        values.get('sdm530_import_energy_active', 0.0) 
    )
        
@webiopi.macro
def getAllSmtp():
    mystring = ''
    for x in l_result:
        mystring += x + ';'
    return mystring

@webiopi.macro
def getAutomationActive():
    global automationActive # Ensure this macro directly returns the current global state
    return automationActive

# --- WebIOPi Setup and Teardown ---
def setup():
    # Make sure all flap GPIOs are defined as outputs
    GPIO.setFunction(19, GPIO.OUT) 
    GPIO.setFunction(26, GPIO.OUT) 
    GPIO.setFunction(16, GPIO.OUT) 
    GPIO.setFunction(20, GPIO.OUT) 
    GPIO.setFunction(RESET_GPIO, GPIO.OUT) # Ensure the reset GPIO is set as output

    # Initialize all GPIOs to LOW (off) at startup for safety
    GPIO.output(19, GPIO.LOW)
    GPIO.output(26, GPIO.LOW)
    GPIO.output(16, GPIO.LOW)
    GPIO.output(20, GPIO.LOW)
    GPIO.output(RESET_GPIO, GPIO.LOW) # Initialize reset GPIO to LOW

    global last_automation_action_time
    last_automation_action_time = time.time() - aktuellesZeitfenster 

    logger.info("WebIOPi setup complete. GPIOs initialized.")

def destroy():
    # Ensure all automation-controlled GPIOs are set to LOW on shutdown
    GPIO.output(19, GPIO.LOW)
    GPIO.output(26, GPIO.LOW)
    GPIO.output(16, GPIO.LOW)
    GPIO.output(20, GPIO.LOW)
    GPIO.output(RESET_GPIO, GPIO.LOW) # Ensure reset GPIO is OFF on destroy
    GPIO.cleanup()
    logger.info("WebIOPi destroy complete. GPIOs cleaned up.")

if __name__=="__main__":
    print("This script is designed to run with WebIOPi. Running it directly might not behave as expected.")
    pass