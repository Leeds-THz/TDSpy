####################################################################
# PACKAGES REQUIRED
####################################################################

# pymeasure
# newportxps
# matplotlib
# PyQt5
# tkinter

####################################################################
# IMPORTS
####################################################################
import XPSHelper as xpsHelp

import logging
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

import sys
import tempfile
# import random
from time import sleep
from pymeasure.log import console_log
from pymeasure.display.Qt import QtWidgets
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import BooleanParameter, IntegerParameter, FloatParameter, Parameter, ListParameter
import matplotlib.pyplot as plt
from pymeasure.instruments.signalrecovery import DSP7265
from newportxps import NewportXPS
import tkinter as tk
from tkinter import filedialog

####################################################################
# GENERAL FUNCTIONS
####################################################################

def ChooseSaveFile():
	# Choose file to save
	root = tk.Tk()
	root.withdraw() # Removes underlying tkinter window

	return filedialog.asksaveasfilename(title = "Select save path",filetypes = (("Data file","*.dat"),("all files","*.*")))

####################################################################
# THz Procedures
####################################################################
class XPSGatheringProcedure(Procedure):
	# Scan Type
	scanType = ListParameter('Scan Type', choices=['XPS - Delay', 'Gathering', 'Goto Delay', 'Goto Cursor'])


	# Scan Inputs
	startDelay = FloatParameter('Start Step', units='ps', default=0)
	stepDelay = FloatParameter('Step Size', units='ps', default=0.01)
	stopDelay = FloatParameter('End Step', units='ps', default=10)

	thzBandwidth = FloatParameter('THz Bandwidth', units='THz', default=15)

	# XPS Inputs
	xpsIP = Parameter('XPS IP', default="192.168.0.254")
	xpsStage = Parameter("XPS Stage", default="element.delay")
	xpsPasses = IntegerParameter("XPS Passes", default = 2)
	xpsZeroOffset = FloatParameter("XPS Zero Offset", units="ps", default=0.0)
	xpsReverse = BooleanParameter("XPS Reverse", default=False)

	# Lockin Inputs
	lockinGPIB = IntegerParameter('Lockin GPIB', default=20)
	lockinControl = BooleanParameter('Control Lockin', default=False)
	lockinWait = FloatParameter('Wait Time', group_by='lockinControl', group_condition=True, units='s', default=20e-3)
	lockinSen = FloatParameter('Sensitivity', group_by='lockinControl', group_condition=True, units='mV', default=100)
	
	
	DATA_COLUMNS = ['Delay', 'X', 'Y']

	def startup(self):
		log.info("Startup")

		# Try and connect to Lock-In
		try:
			# Connect to the given GPIB port
			self.lockin = DSP7265("GPIB::{}".format(self.lockinGPIB))
			sleep(0.1)

			if self.lockinControl:
				# Set time constant
				log.info("Setting the Time Constant to %s A" % self.lockinWait)
				self.lockin.time_constant=self.lockinWait
				sleep(0.1)

				# Set sensitivity
				log.info("Setting the sensitivity to %s A" % self.lockinSen)
				self.lockin.sensitivity=(self.lockinSen / 1000)
				sleep(0.1)

		except Exception as e:
			log.error("Lockin initialisation failed")
			log.error(str(e))
			log.error(str(e.args))

		# Try and connect to XPS
		try:
			self.xps = xpsHelp.InitXPS(self.xpsIP)
		except Exception as e:
			log.error("XPS initialisation failed")
			log.error(str(e))
			log.error(str(e.args))
		

	def execute(self):
		log.info("Initialising gathering")
		err, msg = xpsHelp.InitXPSGathering(self.xps, self.xpsStage, self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse, self.thzBandwidth, self.lockin.time_constant)
		
		# Check for errors
		if err != 0:
			# Get XPS error string
			log.error(xpsHelp.GetXPSErrorString(self.xps, err))
			# self.update_status(Procedure.FAILED)
			self.emit('status', Procedure.FAILED)
			return

		self.emit('progress', 5)

		log.info("Running gathering")
		err, msg = xpsHelp.RunGathering(self.xps, self.xpsStage, self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse)
		
		# Check for errors
		if err != 0:
			# Get XPS error string
			log.error(xpsHelp.GetXPSErrorString(self.xps, err))
			# self.update_status(Procedure.FAILED)
			self.emit('status', Procedure.FAILED)
			return

		self.emit('progress', 90)

		log.info("Downloading gathering file")
		xpsHelp.GetGatheringFile(self.xps)

		self.emit('progress', 95)

		log.info("Reading gathering file")
		data = xpsHelp.ReadGathering(self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse, self.lockinSen)

		# Emit data one index at a time
		for i in range(len(data["Delay"])):
			curData = {'Delay': data["Delay"][i], 'X': data["X"][i], 'Y': data["Y"][i]}
			self.emit('results', curData)

####################################################################
# Main Window
####################################################################
class GatheringWindow(ManagedWindow):
	def __init__(self):
		super().__init__(
			procedure_class=XPSGatheringProcedure,
			inputs=['scanType','startDelay','stepDelay','stopDelay','thzBandwidth','xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse','lockinGPIB', 'lockinControl', 'lockinWait','lockinSen'],
			displays=['scanType','startDelay','stepDelay','stopDelay','thzBandwidth','xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse','lockinGPIB','lockinControl', 'lockinWait','lockinSen'],
			x_axis='Delay',
			y_axis='X',
			sequencer=True,
            sequencer_inputs=['startDelay', 'stopDelay'],
			hide_groups = True
			)
		self.setWindowTitle('THz Scan')

	def queue(self, procedure=None):
		filename = ChooseSaveFile()

		if procedure is None:
			procedure = self.make_procedure()

		# procedure = self.make_procedure()
		results = Results(procedure, filename)
		experiment = self.new_experiment(results)

		self.manager.queue(experiment)

####################################################################
# Main
####################################################################

if __name__ == "__main__":
	app = QtWidgets.QApplication(sys.argv)
	window = GatheringWindow()
	window.show()
	sys.exit(app.exec())
