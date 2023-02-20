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
import logging
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

import os
import sys
import tempfile
# import random
from time import sleep
from pymeasure.log import console_log
from pymeasure.display.Qt import QtWidgets
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import BooleanParameter, IntegerParameter, FloatParameter, Parameter, ListParameter
import numpy as np
import matplotlib.pyplot as plt
from pymeasure.instruments.signalrecovery import DSP7265
from newportxps import NewportXPS
import math
import csv
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
# XPS FUNCTIONS
####################################################################

def ConvertPsToMm(ps, zeroOffset, passes, reverse):
	c = 0.3 # Speed of light in mm/ps

	if reverse:
		return (-1 * c * (1 / passes) * ps) + zeroOffset
	else:
		return (c * (1 / passes) * ps) + zeroOffset

def ConvertMmToPs(mm, zeroOffset, passes, reverse):
	c = 0.3 # Speed of light in mm/ps

	if reverse:
		return ((mm - zeroOffset) * passes) / -c
	else:
		return ((mm - zeroOffset) * passes) / c

def GetBandwidthStageSpeed(bandwidth, tc, tcToWait, passes):
	# This code is taken from Josh's THz scan program
	minSamplingPeriod = 1 / (bandwidth * 2) # ps
	maxStageSpeed = minSamplingPeriod / (tc * tcToWait) # ps/s
	
	return maxStageSpeed * 0.3 * (1 / passes) # mm/s

def InitXPS(ip, user = "Administrator", password = "Administrator"):
	os.system("ssh-keyscan {} > {}\\.ssh\\known_hosts.".format(ip, os.path.expanduser('~')))

	xps = NewportXPS(ip, username=user, password=password)

	return xps

def GetGatheringFile(xps, localFile = None):
	# Delete existing gathering file
	if localFile == None:
		localFile = 'Gathering.dat'
	
	if os.path.exists(localFile):
		os.remove(localFile)

	xps.ftpconn.connect()

	xps.ftpconn._conn.get('/Admin/Public/Gathering/Gathering.dat', localFile)


def InitXPSGathering(xps, stage, startDelay, stepDelay, stopDelay, zeroOffset, passes, reverse, bandwidth, tc, tcToWait = 4):
	scanStageSpeed = GetBandwidthStageSpeed(bandwidth, tc, tcToWait, passes) # mm/s
	scanSteps = ConvertPsToMm(stepDelay, 0, passes, False) # mm
	scanPeriod = scanSteps / scanStageSpeed # s

	expectedPoints = int(math.floor(((stopDelay - startDelay) / stepDelay) + 2))
	xpsDivisor = int(math.floor(scanPeriod * 10000))

	# Get max velocity settings
	maxVeloAcc = xps._xps.PositionerMaximumVelocityAndAccelerationGet(xps._sid, stage)

	# Set velocity to max
	err, msg = xps._xps.PositionerSGammaParametersSet(xps._sid, stage, maxVeloAcc[1], maxVeloAcc[2], 0.005, 0.05)

	# Check for errors
	if err != 0:
		return err, msg

	# Move stage to start pos
	xps.move_stage(stage, ConvertPsToMm(startDelay, zeroOffset, passes, reverse))

	# Set stage velocity based on required THz bandwidth
	err, msg = xps._xps.PositionerSGammaParametersSet(xps._sid, stage, scanStageSpeed, maxVeloAcc[2], 0.005, 0.05)

	# Check for errors
	if err != 0:
		return err, msg


	# Reset gathering
	err, msg = xps._xps.GatheringReset(xps._sid)

	# Check for errors
	if err != 0:
		return err, msg

	# Set gathering config
	err, msg = xps._xps.GatheringConfigurationSet(xps._sid, ["{}.CurrentPosition".format(stage), "GPIO4.ADC1", "GPIO4.ADC2"])

	# Check for errors
	if err != 0:
		return err, msg

	# Set event trigger
	err, msg = xps._xps.EventExtendedConfigurationTriggerSet(xps._sid, ("{}.SGamma.MotionStart".format(stage),), ("",), ("",), ("",), ("",))

	# Check for errors
	if err != 0:
		return err, msg

	# Set event action
	err, msg = xps._xps.EventExtendedConfigurationActionSet(xps._sid, ("GatheringRun",), (str(expectedPoints),), (str(xpsDivisor),), ("",), ("",))

	# Check for errors
	if err != 0:
		return err, msg

	# Event ext. Start
	err, msg = xps._xps.EventExtendedStart(xps._sid)

	# Check for errors
	return err, msg
	
	

def RunGathering(xps, stage, startDelay, stepDelay, stopDelay, zeroOffset, passes, reverse, localFile = None):
	# Move to end position
	xps.move_stage(stage, ConvertPsToMm(stopDelay, zeroOffset, passes, reverse))

	# Gathering stop + save
	err, msg = xps._xps.GatheringStopAndSave(xps._sid)

	# Check for errors
	if err != 0:
		return err, msg

	# Get gathering file
	GetGatheringFile(xps, localFile)

	return err, msg
	
def ReadGathering(startDelay, stepDelay, stopDelay, zeroOffset, passes, reverse, lockinSensitivity, localFile = None, headerLines = 2):
	if localFile == None:
		localFile = "Gathering.dat"
	
	# Empty variables to store gathering data to
	delay = []
	sigX = []
	sigY = []

	# Open gathering file
	with open(localFile, mode='r') as dataFile:
		dataReader = csv.reader(dataFile, delimiter='\t')

		# Skip header lines
		for i in range(headerLines):
			next(dataReader, None)

		# Read file row-by-row
		for row in dataReader:
			# Store data to variables
			delay.append(ConvertMmToPs(float(row[0]), zeroOffset, passes, reverse))
			sigX.append(float(row[1]) * lockinSensitivity * 0.1)
			sigY.append(float(row[2]) * lockinSensitivity * 0.1)

	# Interpolate data
	delayInterp = np.arange(startDelay, stopDelay + stepDelay, stepDelay)
	xInterp = np.interp(delayInterp, delay, sigX)
	yInterp = np.interp(delayInterp, delay, sigY)

	return {"Delay": delayInterp, "X": xInterp, "Y": yInterp}

def GetXPSErrorString(xps, errorCode):
	# Check for errors
	if errorCode != 0:
		# Get XPS error string
		_, errString = xps._xps.ErrorStringGet(xps._sid, errorCode)

		return errString
	else:
		return "No XPS Error"


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
			self.xps = InitXPS(self.xpsIP)
		except Exception as e:
			log.error("XPS initialisation failed")
			log.error(str(e))
			log.error(str(e.args))
		

	def execute(self):
		log.info("Initialising gathering")
		err, msg = InitXPSGathering(self.xps, self.xpsStage, self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse, self.thzBandwidth, self.lockin.time_constant)
		
		# Check for errors
		if err != 0:
			# Get XPS error string
			log.error(GetXPSErrorString(self.xps, err))
			# self.update_status(Procedure.FAILED)
			self.emit('status', Procedure.FAILED)
			return

		self.emit('progress', 5)

		log.info("Running gathering")
		err, msg = RunGathering(self.xps, self.xpsStage, self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse)
		
		# Check for errors
		if err != 0:
			# Get XPS error string
			log.error(GetXPSErrorString(self.xps, err))
			# self.update_status(Procedure.FAILED)
			self.emit('status', Procedure.FAILED)
			return

		self.emit('progress', 90)

		log.info("Downloading gathering file")
		GetGatheringFile(self.xps)

		self.emit('progress', 95)

		log.info("Reading gathering file")
		data = ReadGathering(self.startDelay, self.stepDelay, self.stopDelay, self.xpsZeroOffset, self.xpsPasses, self.xpsReverse, self.lockinSen)

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
