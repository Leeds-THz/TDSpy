####################################################################
# PACKAGES REQUIRED
####################################################################

# pymeasure
# newportxps
# matplotlib
# PyQt5
# pywin32

####################################################################
# IMPORTS
####################################################################
import XPSHelper as xpsHelp

import logging
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

import sys
import tempfile
from time import sleep
from pymeasure.log import console_log
from pymeasure.display.Qt import QtWidgets
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import BooleanParameter, IntegerParameter, FloatParameter, Parameter, ListParameter
import matplotlib.pyplot as plt
from pymeasure.instruments.signalrecovery import DSP7265
from pymeasure.instruments.keithley import Keithley2400
from newportxps import NewportXPS
# import tkinter as tk
# from tkinter import filedialog
import numpy as np
import shutil
import os
import win32ui

####################################################################
# GENERAL FUNCTIONS
####################################################################

def ChooseSaveFile():
	# Choose file to save
	dlg = win32ui.CreateFileDialog( 1, ".dat", "", 0, "Data Files (*.data)|*.dat|All Files (*.*)|*.*|")
	dlg.DoModal()
	return dlg.GetPathName()

# def GetFFTAbs(x, y):
# 	N = len(x)

# 	fftFull = fft(y)
# 	freq = fftfreq(N, x[1]-x[0])[:N//2]
# 	fftAbs = 2.0/N * np.abs(fftFull[0:N//2])

# 	return freq, fftAbs

####################################################################
# THz Procedures
####################################################################
class TDSProcedure(Procedure):
	# Scan Type
	scanType = ListParameter('Scan Type', choices=['Step Scan', 'Gathering', 'Goto Delay', 'Read Lockin'])

	# Scan Inputs
	startDelay = FloatParameter('Start Step', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=0)
	stepDelay = FloatParameter('Step Size', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=0.01)
	stopDelay = FloatParameter('End Step', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=10)

	gotoDelay = FloatParameter('Goto Delay', group_by='scanType', group_condition='Goto Delay', units='ps', default=0)

	thzBandwidth = FloatParameter('THz Bandwidth', group_by='scanType', group_condition='Gathering', units='THz', default=15)

	# XPS Inputs
	xpsIP = Parameter('XPS IP', group_by='scanType', group_condition=lambda v: v != 'Read Lockin', default="192.168.0.254")
	xpsStage = Parameter("XPS Stage", group_by='scanType', group_condition=lambda v: v != 'Read Lockin', default="element.delay")
	xpsPasses = IntegerParameter("XPS Passes", group_by='scanType', group_condition=lambda v: v != 'Read Lockin', default = 2)
	xpsZeroOffset = FloatParameter("XPS Zero Offset", group_by='scanType', group_condition=lambda v: v != 'Read Lockin', units="ps", default=0.0)
	xpsReverse = BooleanParameter("XPS Reverse", group_by='scanType', group_condition=lambda v: v != 'Read Lockin', default=False)

	# XPS 2 Inputs

	xps2Control = BooleanParameter('Control XPS 2', group_by='scanType', group_condition=lambda v: v != 'Read Lockin', default=False)

	xps2Stage = Parameter("XPS 2 Stage", group_by='xps2Control', group_condition=True, default="pump.delay")
	xps2Passes = IntegerParameter("XPS 2 Passes", group_by='xps2Control', group_condition=True, default = 2)
	xps2ZeroOffset = FloatParameter("XPS 2 Zero Offset", group_by='xps2Control', group_condition=True, units="ps", default=0.0)
	xps2Reverse = BooleanParameter("XPS 2 Reverse", group_by='xps2Control', group_condition=True, default=False)
	
	xps2Delay = FloatParameter('XPS 2 Delay', group_by='xps2Control', group_condition=True, units='ps', default=0)

	# Lockin Inputs
	lockinGPIB = IntegerParameter('Lockin GPIB', group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default=20)
	lockinControl = BooleanParameter('Control Lockin', group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default=False)
	lockinWait = FloatParameter('Wait Time', group_by='lockinControl', group_condition=True, units='s', default=20e-3)
	lockinSen = FloatParameter('Sensitivity', group_by='lockinControl', group_condition=True, units='mV', default=100)
	

	# Keithley Voltage
	keithleyControl = BooleanParameter('Control Keithley Voltage', group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default=False)
	keithleyGPIB = IntegerParameter('Keithley GPIB', group_by='keithleyControl', group_condition=True, default=15)
	keithleyVoltage = FloatParameter('Keithley Voltage', group_by='keithleyControl', group_condition=True, default=0)


	# Auto file naming
	autoFileNameControl = BooleanParameter('Auto Name File', group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default=False)
	autoFileBaseName = Parameter('Auto Filename Base', group_by='autoFileNameControl', group_condition=True, default="")

	# filename = Parameter("Save File Path", default="temp.dat")


	DATA_COLUMNS = ['Delay', 'X', 'Y']

	data = {'Delay': [], 'X':[], 'Y':[]}

	saveOnShutdown = False

	def startup(self):
		log.info("Startup")

		if self.scanType != 'Goto Delay':
			# Try and connect to Lock-In
			try:
				# Connect to the given GPIB port
				log.info("Connecting to Lockin")
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

			# Try and connect to Keithley Voltage
			if self.keithleyControl:
				try:
					# Connect to the given GPIB port
					log.info("Connecting to Keithley")
					self.keithley = Keithley2400("GPIB::{}".format(self.keithleyGPIB))
					sleep(0.1)

					# Set the voltage
					log.info("Setting the voltage to %s V" % self.keithleyVoltage)
					self.keithley.source_voltage = self.keithleyVoltage
				
				except Exception as e:
					log.error("Keithley initialisation failed")
					log.error(str(e))
					log.error(str(e.args))

		if self.scanType != 'Read Lockin':
			# Try and connect to XPS
			try:
				log.info("Connecting to XPS")
				self.xps = xpsHelp.InitXPS(self.xpsIP)
			except Exception as e:
				log.error("XPS initialisation failed")
				log.error(str(e))
				log.error(str(e.args))

			# Move XPS 2 to the given delay
			if self.xps2Control:
				log.info("Moving XPS 2")
				err, msg = xpsHelp.GotoDelay(self.xps, self.xps2Stage, self.xps2Delay, self.xps2ZeroOffset, self.xps2Passes, self.xps2Reverse)

				# Check for errors
				if err != 0:
					# Get XPS error string
					log.error(xpsHelp.GetXPSErrorString(self.xps, err))
					self.emit('status', Procedure.FAILED)
					return

	def executeReadLockin(self):
		# Get the lockin time constant
		tc = self.lockin.time_constant

		# Set wait time between measurements (tc * 2)
		waitTime = tc * 2

		# Counter used to track progress
		counter = 0

		# Read lockin until stop command is given
		while(True):
			if self.should_stop():
				break

			self.data['Delay'].append(counter * waitTime)

			# Take measurement from lockin
			self.data['X'].append(self.lockin.x * 1000) # Convert to mV
			self.data['Y'].append(self.lockin.y * 1000) # Convert to mV

			# Wait 2 time constants
			sleep(waitTime)

			curData = {'Delay': self.data["Delay"][counter], 'X': self.data["X"][counter], 'Y': self.data["Y"][counter]}

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
		
		# Counter used to track progress
		counter = 0

		log.info("Starting step scan")

		# Iterate through the delay positions
		for delay in delayPoints:
			if self.should_stop():
				break

			# Move to delay
			self.xps.move_stage(self.xpsStage, xpsHelp.ConvertPsToMm(delay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse))

			self.data['Delay'].append(delay)

			# Wait 2 time constants
			sleep(waitTime)

			# Take measurement from lockin
			self.data['X'].append(self.lockin.x * 1000) # Convert to mV
			self.data['Y'].append(self.lockin.y * 1000) # Convert to mV

			curData = {'Delay': self.data["Delay"][counter], 'X': self.data["X"][counter], 'Y': self.data["Y"][counter]}

			# Emit data
			self.emit('results', curData)

			# Update progress
			self.emit('progress', ((counter + 1) / len(delayPoints)) * 100)

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
		self.data = xpsHelp.ReadGathering(self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse, self.lockinSen)

		if self.should_stop():
			return

		# Emit data one index at a time
		for i in range(len(self.data["Delay"])):
			curData = {'Delay': self.data["Delay"][i], 'X': self.data["X"][i], 'Y': self.data["Y"][i]}
			self.emit('results', curData)
	
	def execute(self):
		if self.scanType == 'Gathering':
			self.saveOnShutdown = True
			self.executeGatheringScan()

		elif self.scanType == 'Step Scan':
			self.saveOnShutdown = True
			self.executeStepScan()

		elif self.scanType == 'Goto Delay':
			self.executeGotoDelay()

		elif self.scanType == 'Read Lockin':
			self.saveOnShutdown = True
			self.executeReadLockin()
	
	def setTempFile(self, tempFilePath):
		self.curTempFile = tempFilePath

	def setDefaultDir(self, path):
		self.defaultDir = path

	def shutdown(self):
		if self.saveOnShutdown:
			if self.autoFileNameControl:
				fileCount = 0

				autoFilePath = os.path.join(self.defaultDir, self.autoFileBaseName)

				# Check if file exists
				# If it does, append number to end and increment
				while os.path.exists(autoFilePath + "_{}".format(fileCount) + ".dat"):
					fileCount += 1

				savepath = autoFilePath + "_{}".format(fileCount) + ".dat"
			else:
				savepath = ChooseSaveFile()
			
			# Check that a file was selected
			if savepath != '':
				log.info("Saving data to " + savepath)
				# Copy the current temp file to the savepath
				shutil.copy(self.curTempFile, savepath)
			else:
				log.info("Data not saved")

####################################################################
# Main Window
####################################################################

class TDSWindow(ManagedWindow):
	def __init__(self):
		super().__init__(
			procedure_class=TDSProcedure,
			inputs=['scanType','startDelay','stepDelay','stopDelay', 'gotoDelay', 'thzBandwidth','xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse', 'xps2Control', 'xps2Stage', 'xps2Passes', 'xps2ZeroOffset', 'xps2Reverse', 'xps2Delay', 'lockinGPIB', 'lockinControl', 'lockinWait','lockinSen', 'keithleyControl', 'keithleyGPIB', 'keithleyVoltage', 'autoFileNameControl', 'autoFileBaseName'],
			displays=['scanType','startDelay','stepDelay','stopDelay', 'gotoDelay', 'thzBandwidth','xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse', 'xps2Control', 'xps2Stage', 'xps2Passes', 'xps2ZeroOffset', 'xps2Reverse', 'xps2Delay', 'lockinGPIB', 'lockinControl', 'lockinWait','lockinSen', 'keithleyControl', 'keithleyGPIB', 'keithleyVoltage', 'autoFileNameControl', 'autoFileBaseName'],
			x_axis='Delay',
			y_axis='X',
			sequencer=True,
            sequencer_inputs=['startDelay', 'stepDelay', 'stopDelay', 'keithleyControl', 'keithleyVoltage'],
			hide_groups = True,
			directory_input=True,
			inputs_in_scrollarea = True
			)
		self.setWindowTitle('THz Scan')
		# self.directory = r'C:/'

		# Get path to temp folder
		self.tempDir = os.path.join(tempfile.gettempdir(), "tdspytemp")

		# Check if temp folder exists
		if os.path.exists(self.tempDir):
			# Remove it (this is to get rid of any old temp files)
			shutil.rmtree(self.tempDir)

		# Create temp folder
		os.mkdir(self.tempDir)

	def queue(self, procedure=None):
		# Create temp file to save data to
		curTempFile = tempfile.mktemp(dir=self.tempDir)

		if procedure is None:
			procedure = self.make_procedure()
		
		# Pass the name of the current temporary file to the procedure
		procedure.setTempFile(curTempFile)

		# Pass the default directory to the procedure
		procedure.setDefaultDir(self.directory)

		# procedure = self.make_procedure()
		results = Results(procedure, curTempFile)
		experiment = self.new_experiment(results)

		# Start the experiment
		self.manager.queue(experiment)

		

####################################################################
# Main
####################################################################

if __name__ == "__main__":
	app = QtWidgets.QApplication(sys.argv)
	window = TDSWindow()
	window.show()
	sys.exit(app.exec())
