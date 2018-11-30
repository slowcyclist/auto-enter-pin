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

import configparser,sys

config = configparser.ConfigParser()
config.read(sys.path[0]+'/'+configfilename)                
time_out = int(config.get('DEFAULT','time_out',fallback=45))
print(  "time_out:",time_out)
sims = [s for s in config.sections() if "sim" in s]
simdic = {"sim1":"/ril_0","sim2":"/ril_1"}
modemdic = {v: k for k, v in simdic.items()}
pin = {}
simcardidentifier = {}
for s in sims :
  pin[simdic[s]] = config.get(s,'pin',fallback="")
  simcardidentifier[simdic[s]] = config.get(s,'simcardidentifier',fallback="")

print(pin) #do not log, just for debug
print(simcardidentifier)

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

logger.info ("imports done...starting")

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
mainloop = GLib.MainLoop()
sys_dbus = dbus.SystemBus()

def modem_added(modem_path, properties):
  logger.info("Modem added %s (= %s)" % (modem_path, modemdic[modem_path]))
  global modem_list
  modem_list.append(modem_path)
  global simmanager
  simmanager[modem_path] = dbus.Interface(sys_dbus.get_object('org.ofono', modem_path),'org.ofono.SimManager')
  global sim_connect
  sim_connect[modem_path] = simmanager[modem_path].connect_to_signal("PropertyChanged", lambda *args : sim_listener(modem_path,*args))
  prop_sim = simmanager[modem_path].GetProperties()
  #in case modem is already inited when the script runs:
  if ("PinRequired" in prop_sim.keys()) and (prop_sim["PinRequired"]=="pin"):
    sim_listener(modem_path, "PinRequired", "pin")      

def sim_listener(modem_path, name, value):
  logger.info("{}: property '{}' changed to '{}'".format(modemdic[modem_path], name, str(dbus2py(value))))
  if (name == "PinRequired") and (value == "pin"):
    prop_sim = simmanager[modem_path].GetProperties()
    if (simcardidentifier[modem_path] !="") and (simcardidentifier[modem_path] != prop_sim["CardIdentifier"]) :
      logger.info("%s CARD CHANGED!!!"%(modemdic[modem_path]))
      #here do something (send email, popup warning, erase sensitive user data...)
      #Do not enter pin as it would spoil an attempt!
      end(True)
    elif pin[modem_path] != "" :  
      try :
        simmanager[modem_path].EnterPin("pin", pin[modem_path])
      except Exception as e:
        logger.info("error entering pin : {}".format(e))
        raise
        end(True)
  if (name == "PinRequired") and (value == "none"):
        sim_connect[modem_path].remove()
        logger.info("%s successfully unlocked!"%(modemdic[modem_path]))
        global modem_list
        modem_list.remove(modem_path)
        if len(modem_list) == 0:
          end(False)
     

def start() :
  time.sleep(5)    #we are started just after ofono... no hurry
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
simmanager = {}
sim_connect = {}
try:
  timeout = GLib.timeout_add_seconds(int(time_out), timed_out)
  start()
  mainloop.run()
except KeyboardInterrupt:
  logger.info('Ctrl+C hit, quitting')
  end(True)



