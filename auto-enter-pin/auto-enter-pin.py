#!/usr/bin/python3

"""
this script is meant to automatically enter the SIM pin on startup on SailfishOS
See readme for installation and configuration

************
P. Joyez copyright 2018
This code is licensed under the GPL v2 or later.
"""
from auto_enter_pin_settings import *

from dbus_types import *

import dbus
import sys, time
from gi.repository import GLib
import dbus.mainloop.glib
import os,logging

logfile="{0}/{1}".format(sys.path[0], "auto-enter-pin.log")
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
  logger.info("Modem added %s" % (modem_path))
  global simmanager
  simmanager = dbus.Interface(sys_dbus.get_object('org.ofono', modem_path),'org.ofono.SimManager')
  global sim_connect
  sim_connect = simmanager.connect_to_signal("PropertyChanged", sim_listener)
  prop_sim = simmanager.GetProperties()
  #in case modem is already inited when the script runs:
  if ("PinRequired" in prop_sim.keys()) and (prop_sim["PinRequired"]=="pin"):
    sim_listener("PinRequired", "pin")      

def sim_listener(name, value):
  logger.info("SIM property: {} changed to {}".format(name, str(dbus2py(value))))
  if (name == "PinRequired") and (value == "pin"):
    prop_sim = simmanager.GetProperties()
    if (simcardidentifier !="") and (simcardidentifier != prop_sim["CardIdentifier"]) :
      logger.info("SIM CARD CHANGED!!!")
      #here do something (send email, popup warning, erase sensitive user data...)
      #Do not enter pin as it would spoil an attempt!
      end(True)
    else :  
      try :
        simmanager.EnterPin("pin", mypin)
      except Exception as e:
        logger.info("error entering pin : {}".format(e))
        raise
        end(True)
  if (name == "PinRequired") and (value == "none"):
        logger.info("success!")
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
  #in case modem is already inited when the script runs:
  if len (modems)>0 :
    modem_added(modems[0][0], modems[0][1])

def end(failed) :
    GLib.source_remove(timeout)
    connect_modem_manager.remove()
    sim_connect.remove()
    if failed :
      logger.info("failed end")
    else : 
      logger.info("normal end")
    mainloop.quit()  

def timed_out() :
  logger.info("timed out!")
  end(True)

try:
  timeout = GLib.timeout_add_seconds(int(time_out), timed_out)
  start()
  mainloop.run()
except KeyboardInterrupt:
  logger.info('Ctrl+C hit, quitting')
  end(True)



