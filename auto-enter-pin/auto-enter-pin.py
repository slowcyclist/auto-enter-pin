#!/usr/bin/python3

"""
this script is meant to automatically enter the SIM pin on startup on SailfishOS
See readme for installation and configuration

************
P. Joyez copyright 2018
This code is licensed under the GPL v2 or later.
"""
logfilename="auto-enter-pin.log"
configfilename='auto-enter-pin.conf'

from dbus_types import *

import dbus
import sys, time
from gi.repository import GLib
import dbus.mainloop.glib
import os,logging

logfile="{0}/{1}".format(sys.path[0], logfilename)
try:
    os.remove(logfile)
except OSError as e:  ## if failed, report it back to the user ##
    print ("Error: %s - %s." % (e.filename, e.strerror))

logging.basicConfig(
    level=logging.INFO,
    #format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(logfile),
        logging.StreamHandler(sys.stdout)
    ])
    
logger = logging.getLogger()

import configparser,sys
configfilename = "{0}/{1}".format(sys.path[0],configfilename)
if not os.path.isfile(configfilename) :
  logger.info ("no configuration file... cannot continue")
  exit(1)

logger.info ("reading configuration")
simdic = {"sim1":"/ril_0","sim2":"/ril_1"}
modemdic = {v: k for k, v in simdic.items()}
config = configparser.ConfigParser()
config.read(configfilename)
config.default_section = 'general'              
time_out = int(config.get('general','time_out',fallback=45))
priority = config.get('general','priority',fallback="")
priority_delay = int(config.get('general','priority_delay',fallback=5))
startup_delay = int(config.get('general','startup_delay',fallback=5))
sims = [s for s in config.sections() if "sim" in s]
simcardidentifier = {}
pin = {}
for s in sims :
  pin[simdic[s]] = config.get(s,'pin',fallback="")
  simcardidentifier[simdic[s]] = config.get(s,'simcardidentifier',fallback="")

print("time_out:",time_out)
print("priority",priority)
print("priority_delay",priority_delay)
if priority != "" :
  priority = simdic[priority]
  time_out += priority_delay
time_out += startup_delay
#print(pin) #do not log, just for debug
#print(simcardidentifier)

logger.info ("imports done...starting")

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
mainloop = GLib.MainLoop()
sys_dbus = dbus.SystemBus()

def modem_added(modem_path, properties):
  modem_path = str (modem_path)
  logger.info("Modem added %s (= %s)" % (modem_path, modemdic[modem_path]))
  #logger.info('initial properties:\n %s'%(dbus2py(properties)))
  global modem_list
  modem_list.append(modem_path)
  global simmanager,sim_connect,sim_properties
  simmanager[modem_path] = dbus.Interface(sys_dbus.get_object('org.ofono', modem_path),'org.ofono.SimManager')
  sim_connect[modem_path] = simmanager[modem_path].connect_to_signal("PropertyChanged", lambda *args : sim_listener(modem_path,*args))
  prop_sim = simmanager[modem_path].GetProperties()
  sim_properties[modem_path] = prop_sim
  #logger.info('\n\nSimmanager initial properties:\n %s'%(dbus2py(prop_sim)))
  #in case modem is already more or less inited when the script runs:
  if ("PinRequired" in prop_sim.keys()) and (prop_sim["PinRequired"]=="pin"):
      sim_listener(modem_path, "PinRequired", "pin")

def sim_listener(modem_path, name, value):
  logger.info("{}: property '{}' changed to '{}'".format(modemdic[modem_path], name, str(dbus2py(value))))
  global sim_properties, prio
  sim_properties[modem_path][name] = value
  prop_sim = sim_properties[modem_path]
  if "CardIdentifier" in prop_sim.keys() :
    if (simcardidentifier[modem_path] !="") and (simcardidentifier[modem_path] != prop_sim["CardIdentifier"]) :
      logger.info("%s CARD CHANGED!!!"%(modemdic[modem_path]))
      #here do something (send email, popup warning, erase sensitive user data...)
      #Do not enter pin as it would spoil an attempt!
      end(True)
    else: 
      if ("pin" not in prop_sim["LockedPins"]) : #on my phone, on boot, LockedPins is changed before the CardIdentifier is known 
        sim_connect[modem_path].remove()
        logger.info("%s not locked: nothing to do"%(modemdic[modem_path]))
        if (modem_path == priority) and len(modem_list) == 2:
              prio = GLib.timeout_add_seconds(priority_delay, unlock_delayed)
        modem_list.remove(modem_path)
        return
      if (prop_sim["PinRequired"] == "pin") and (modem_path not in unlocked) :
        if pin[modem_path] != "" :
          if (priority != "") and (modem_path != priority):
            global on_hold
            on_hold.append(modem_path)
            logger.info("%s put on hold"%(modemdic[modem_path])) 
          else :
            unlock (modem_path)
        else :
          logger.info("%s is locked but pin is not in config file!"%(modemdic[modem_path]))
          unlocked.append(modem_path)
        return
      if (name == "PinRequired") and (value == "none"): #only consider present event (dont look up the dictionnary as it may not yet be accurate)
        sim_connect[modem_path].remove()
        logger.info("%s successfully unlocked!"%(modemdic[modem_path]))
        if (priority != "") and (modem_path == priority) and len(modem_list) == 2:
          prio = GLib.timeout_add_seconds(priority_delay, unlock_delayed)
        modem_list.remove(modem_path)
        if len(modem_list) == 0:
          end(False)
       
def unlock_delayed ():           
  logger.info("priority delay expired") 
  GLib.source_remove(prio)
  if len(on_hold) > 0 :
    unlock (on_hold[0])
  else :
    logger.info("no sim on hold")

def unlock (modem_path):
  logger.info("unlocking %s"%(modemdic[modem_path])) 
  try :
    simmanager[modem_path].EnterPin("pin", pin[modem_path])
    unlocked.append(modem_path)
  except Exception as e:
    logger.info("error entering pin : {}".format(e))
    raise
    end(True)
 

def start() :
  time.sleep(startup_delay)    #we are started just after ofono... no hurry
#for Xperia X it takes a bit more than 6 secs before the modem is listed
  try:
    manager = dbus.Interface(sys_dbus.get_object('org.ofono', '/'), 'org.ofono.Manager')
    global connect_modem_manager
    connect_modem_manager = manager.connect_to_signal("ModemAdded", modem_added)
    modems = manager.GetModems()
  except Exception as e:
    logger.info("Can't Get modems from manager: {}".format(e))
    end(True)
  logger.info("number of modems found : %s" %(len(modems)))
  #in case modems are already inited when the script starts:
  if len (modems)>0 :
    for m in modems :
      modem_added(m[0], m[1])

def end(failed) :
    GLib.source_remove(timeout)
    connect_modem_manager.remove()
    for m in modem_list:
      sim_connect[m].remove()
    if failed :
      logger.info("failed or timed out")
    else : 
      logger.info("normal end")
    mainloop.quit()  

def timed_out() :
  logger.info("timed out!")
  end(True)

modem_list = []
on_hold = []
unlocked = []
simmanager = {}
sim_connect = {}
sim_properties = {'/ril_0':{} , '/ril_1':{}}
try:
  timeout = GLib.timeout_add_seconds(int(time_out), timed_out)
  start()
  mainloop.run()
except KeyboardInterrupt:
  logger.info('Ctrl+C hit, quitting')
  end(True)



