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
import numpy as np

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
class TDSProcedure(Procedure):
	# Scan Type
	scanType = ListParameter('Scan Type', choices=['Step Scan', 'Gathering', 'Goto Delay', 'Goto Cursor', 'Read Lockin'])

	# Scan Inputs
	startDelay = FloatParameter('Start Step', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=0)
	stepDelay = FloatParameter('Step Size', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=0.01)
	stopDelay = FloatParameter('End Step', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=10)

	gotoDelay = FloatParameter('Goto Delay', group_by='scanType', group_condition='Goto Delay', units='ps', default=0)

	thzBandwidth = FloatParameter('THz Bandwidth', group_by='scanType', group_condition='Gathering', units='THz', default=15)

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

	def executeReadLockin(self):
		# Get the lockin time constant
		tc = self.lockin.time_constant

		# Set wait time between measurements (tc * 2)
		waitTime = tc * 2

		# Create dictionary to store data to
		curData = {'Delay': 0, 'X': 0, 'Y': 0}

		# Counter used to track progress
		counter = 0

		# Read lockin until stop command is given
		while(True):
			if self.should_stop():
				break

			curData['Delay'] = counter * waitTime

			# Take measurement from lockin
			curData['X'] = self.lockin.x
			curData['y'] = self.lockin.y

			# Wait 2 time constants
			sleep(waitTime)

			# Emit data
			self.emit('results', curData)

			counter += 1


	def executeGotoDelay(self):
		# Goto Delay
		log.info("Moving to delay")
		err, msg = xpsHelp.GotoDelay(self.xps, self.xpsStage, self.gotoDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse)

		# Check for errors
		if err != 0:
			# Get XPS error string
			log.error(xpsHelp.GetXPSErrorString(self.xps, err))
			self.emit('status', Procedure.FAILED)
			return

		# Update progress
		self.emit('progress', 100)


	def executeStepScan(self):
		# Init step scan
		log.info("Initialising step scan")
		err, msg = xpsHelp.GotoDelay(self.xps, self.xpsStage, self.startDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse)
		
		# Check for errors
		if err != 0:
			# Get XPS error string
			log.error(xpsHelp.GetXPSErrorString(self.xps, err))
			self.emit('status', Procedure.FAILED)
			return

		# Create array of delay points
		delayPoints = np.arange(self.startDelay, self.stopDelay, self.stepDelay)

		# Get the lockin time constant
		tc = self.lockin.time_constant

		# Set wait time between measurements (tc * 2)
		waitTime = tc * 2

		# Create dictionary to store data to
		curData = {'Delay': 0, 'X': 0, 'Y': 0}
		
		# Counter used to track progress
		counter = 1

		log.info("Starting step scan")

		# Iterate through the delay positions
		for delay in delayPoints:
			if self.should_stop():
				break

			# Move to delay
			self.xps.move_stage(self.xpsStage, xpsHelp.ConvertPsToMm(delay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse))

			curData['Delay'] = delay

			# Wait 2 time constants
			sleep(waitTime)

			# Take measurement from lockin
			curData['X'] = self.lockin.x
			curData['y'] = self.lockin.y

			# Emit data
			self.emit('results', curData)

			# Update progress
			self.emit('progress', (counter / len(delayPoints)) * 100)

			counter += 1


	def executeGatheringScan(self):
		log.info("Initialising gathering")
		err, msg = xpsHelp.InitXPSGathering(self.xps, self.xpsStage, self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse, self.thzBandwidth, self.lockin.time_constant)
		
		# Check for errors
		if err != 0:
			# Get XPS error string
			log.error(xpsHelp.GetXPSErrorString(self.xps, err))
			self.emit('status', Procedure.FAILED)
			return

		self.emit('progress', 5)

		if self.should_stop():
			return

		log.info("Running gathering")
		err, msg = xpsHelp.RunGathering(self.xps, self.xpsStage, self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse)
		
		# Check for errors
		if err != 0:
			# Get XPS error string
			log.error(xpsHelp.GetXPSErrorString(self.xps, err))
			self.emit('status', Procedure.FAILED)
			return

		self.emit('progress', 90)

		if self.should_stop():
			return

		log.info("Downloading gathering file")
		xpsHelp.GetGatheringFile(self.xps)

		self.emit('progress', 95)

		if self.should_stop():
			return

		log.info("Reading gathering file")
		data = xpsHelp.ReadGathering(self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse, self.lockinSen)

		if self.should_stop():
			return

		# Emit data one index at a time
		for i in range(len(data["Delay"])):
			curData = {'Delay': data["Delay"][i], 'X': data["X"][i], 'Y': data["Y"][i]}
			self.emit('results', curData)
	
	def execute(self):
		if self.scanType == 'Gathering':
			self.executeGatheringScan()
		elif self.scanType == 'Step Scan':
			self.executeStepScan()
		elif self.scanType == 'Goto Delay':
			self.executeGotoDelay()
		elif self.scanType == 'Read Lockin':
			self.executeReadLockin()

####################################################################
# Main Window
####################################################################
class TDSWindow(ManagedWindow):
	def __init__(self):
		super().__init__(
			procedure_class=TDSProcedure,
			inputs=['scanType','startDelay','stepDelay','stopDelay', 'gotoDelay', 'thzBandwidth','xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse','lockinGPIB', 'lockinControl', 'lockinWait','lockinSen'],
			displays=['scanType','startDelay','stepDelay','stopDelay', 'gotoDelay', 'thzBandwidth','xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse','lockinGPIB','lockinControl', 'lockinWait','lockinSen'],
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
	window = TDSWindow()
	window.show()
	sys.exit(app.exec())
