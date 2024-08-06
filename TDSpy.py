####################################################################
# PACKAGES REQUIRED
####################################################################

# pymeasure
# newportxps
# PyQt5
# pywin32
# scipy
# matplotlib
# pylablib (use lightweight installation)
# numba

####################################################################
# IMPORTS
####################################################################
import XPSHelper as xpsHelp
import TDSProcedure as tdsProc

import logging
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

import sys
import tempfile
from time import sleep
from pymeasure.log import console_log
from pymeasure.display.Qt import QtWidgets
from pymeasure.display.windows import ManagedWindow
# from pymeasure.display.windows.managed_dock_window import ManagedDockWindow
from pymeasure.experiment import Procedure, Results, unique_filename
from pymeasure.experiment import BooleanParameter, IntegerParameter, FloatParameter, Parameter, ListParameter
import matplotlib.pyplot as plt
from pymeasure.instruments.signalrecovery import DSP7265
from pymeasure.instruments.keithley import Keithley2400
from newportxps import NewportXPS
import numpy as np
import shutil
import os
import win32ui
from scipy.fft import fft, fftfreq
import csv
from pylablib.devices import Thorlabs
from datetime import datetime, timedelta
import json


####################################################################
# GENERAL FUNCTIONS
####################################################################

def LoadSettings():
	# opening the file in read mode 
	with open("settings.ini", "r") as my_file:
		# reading the file 
		data = my_file.read() 

	return json.loads(data)

def SaveSettings(settings):
	# Serialise
	jsonObject = json.dumps(settings, indent=4)

	# Write file
	with open("settings.ini", "w") as my_file:
		my_file.write(jsonObject)


####################################################################
# Main Window
####################################################################


# class TDSWindow(ManagedDockWindow):
class TDSWindow(ManagedWindow):
	def __init__(self):
		super().__init__(
			procedure_class=tdsProc.TDSProcedure,
			inputs=['scanType','startDelay','stepDelay','stopDelay', 'repeats', 'gotoDelay', 'thzBandwidth', 'preScanWait', 'xpsAnalogueGain', 'xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse', 'xps2Control', 'xps2Stage', 'xps2Passes', 'xps2ZeroOffset', 'xps2Reverse', 'xps2Delay', 'xps2Follow', 'lockinGPIB', 'lockinControl', 'lockinWait','lockinSen', 'keithleyControl', 'keithleyGPIB', 'keithleyVoltage', 'filterControl', 'filterAddress', 'filterPosition', 'autoFileNameControl', 'autoFileBaseName', 'outputFormat', 'sequenceRepeats'],
			displays=['scanType','startDelay','stepDelay','stopDelay', 'repeats', 'xpsStage', 'xps2Control', 'xps2Stage', 'xps2Delay', 'xps2Follow', 'lockinControl', 'keithleyControl', 'keithleyVoltage', 'filterControl', 'filterPosition'],
			x_axis='Delay',
			y_axis='X',
			sequencer=True,
            sequencer_inputs=['startDelay', 'stepDelay', 'stopDelay', 'xps2Delay', 'keithleyVoltage', 'filterPosition', 'preScanWait', 'sequenceRepeats'],
			hide_groups = True,
			# directory_input=True,
			inputs_in_scrollarea = True
			)
		self.setWindowTitle('THz Scan')

		self.settings = LoadSettings()

		self.filename = self.settings["default_filename"]  # Sets default filename
		self.directory = self.settings["default_directory"] # Sets default directory
		self.store_measurement = True                              # Controls the 'Save data' toggle
		self.file_input.extensions = ["dat", "csv", "txt"]         # Sets recognized extensions, first entry is the default extension
		self.file_input.filename_fixed = False                      # Controls whether the filename-field is frozen (but still displayed)

		self.xps = None

	def queue(self, procedure=None):
		# Connect to XPS if unconnected
		if self.xps == None:
			self.xps = xpsHelp.InitXPS(self.inputs.xpsIP.parameter.value)

		if procedure is None:
			procedure = self.make_procedure()

		# Pass the XPS instance
		procedure.setXPS(self.xps)

		# Pass the save location
		procedure.setSaveLocation(unique_filename(
                    self.directory,
                    prefix=self.file_input.filename_base,
                    datetimeformat="",
                    procedure=procedure,
                    ext=self.file_input.filename_extension,
                ))

		# Check if settings file should be overwritten
		overwriteSettings = False

		if self.settings['overwrite_default_directory_on_run'] and self.settings['default_directory'] != self.directory:
			self.settings['default_directory'] = self.directory
			overwriteSettings = True
		if self.settings['overwrite_default_filename_on_run'] and self.settings['default_filename'] != self.file_input.filename_base:
			self.settings['default_filename'] = self.file_input.filename_base
			overwriteSettings = True
		
		if overwriteSettings:
			SaveSettings(self.settings)

		# Call parent queue function to start the procedure + save data etc.
		super().queue(procedure)

		

####################################################################
# Main
####################################################################

if __name__ == "__main__":
	app = QtWidgets.QApplication(sys.argv)
	window = TDSWindow()
	window.show()
	sys.exit(app.exec())
