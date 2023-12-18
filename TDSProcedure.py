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
# from pymeasure.display.windows.managed_dock_window import ManagedDockWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import BooleanParameter, IntegerParameter, FloatParameter, Parameter, ListParameter
import matplotlib.pyplot as plt
from newportxps import NewportXPS
import numpy as np
import shutil
import os
import win32ui
from scipy.fft import fft, fftfreq
import csv
from datetime import datetime, timedelta
from mcculw import ul
from mcculw.enums import ULRange
from mcculw.ul import ULError

####################################################################
# GENERAL FUNCTIONS
####################################################################

def ChooseSaveFile():
	# Choose file to save
	dlg = win32ui.CreateFileDialog( 1, ".dat", "", 0, "Data Files (*.dat)|*.dat|All Files (*.*)|*.*|")
	dlg.DoModal()
	return dlg.GetPathName()

def GetFFTAbs(x, y):
	N = len(x)

	fftFull = fft(y)
	freq = fftfreq(N, x[1]-x[0])
	fftAbs = 2.0/N * np.abs(fftFull)

	return freq, fftAbs

####################################################################
# THz Procedures
####################################################################
class TDSProcedure(Procedure):
	# Scan Type
	scanType = ListParameter('Scan Type', choices=['Step Scan', 'Goto Delay', 'Read DAC'])

	# Scan Inputs
	startDelay = FloatParameter('Start Step', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=0)
	stepDelay = FloatParameter('Step Size', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=0.01)
	stopDelay = FloatParameter('End Step', group_by='scanType', group_condition=lambda v: v == 'Step Scan' or v == 'Gathering', units='ps', default=10)

	gotoDelay = FloatParameter('Goto Delay', group_by='scanType', group_condition='Goto Delay', units='ps', default=0)

	thzBandwidth = FloatParameter('THz Bandwidth', group_by='scanType', group_condition='Gathering', units='THz', default=15)

	# XPS Inputs
	xpsIP = Parameter('XPS IP', group_by='scanType', group_condition=lambda v: v != 'Read DAC', default="192.168.0.254")
	xpsStage = Parameter("XPS Stage", group_by='scanType', group_condition=lambda v: v != 'Read DAC', default="THz_long.PP")
	xpsPasses = FloatParameter("XPS Passes", group_by='scanType', group_condition=lambda v: v != 'Read DAC', default = 2.0)
	xpsZeroOffset = FloatParameter("XPS Zero Offset", group_by='scanType', group_condition=lambda v: v != 'Read DAC', units="ps", default=0.0)
	xpsReverse = BooleanParameter("XPS Reverse", group_by='scanType', group_condition=lambda v: v != 'Read DAC', default=False)

	# XPS 2 Inputs
	xps2Control = BooleanParameter('Control XPS 2', group_by='scanType', group_condition=lambda v: v != 'Read DAC', default=False)

	xps2Stage = Parameter("XPS 2 Stage", group_by='xps2Control', group_condition=True, default=" THz_short.PP")
	xps2Passes = FloatParameter("XPS 2 Passes", group_by='xps2Control', group_condition=True, default = 2.0)
	xps2ZeroOffset = FloatParameter("XPS 2 Zero Offset", group_by='xps2Control', group_condition=True, units="ps", default=0.0)
	xps2Reverse = BooleanParameter("XPS 2 Reverse", group_by='xps2Control', group_condition=True, default=False)
	
	xps2Delay = FloatParameter('XPS 2 Delay', group_by='xps2Control', group_condition=True, units='ps', default=0)
	
	# MCCDAQ
	mccdacBoard = IntegerParameter('MCCDAQ Board Number', group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default=0)
	mccdacXChannel = IntegerParameter('MCCDAQ Lockin X Channel', group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default=0)
	mccdacYChannel = IntegerParameter('MCCDAQ Lockin Y Channel', group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default=1)

	# Lockin Info
	dacWait = FloatParameter('Lockin wait time',  group_by='scanType', group_condition=lambda v: v != 'Goto Delay',  default=0.1,  units='s')

	lockinSen = FloatParameter('Lockin sensitivity',  group_by='scanType', group_condition=lambda v: v != 'Goto Delay',  default=500,  units='mV')

	# Auto file naming
	autoFileNameControl = BooleanParameter('Auto Name File', group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default=False)
	autoFileBaseName = Parameter('Auto Filename Base', group_by='autoFileNameControl', group_condition=True, default=" ")

	# Save File Format 
	outputFormat = ListParameter('Output Format', choices=['Josh File', 'pymeasure'], group_by='scanType', group_condition=lambda v: v != 'Goto Delay', default='Josh File')

	# Repeat 
	# NOTE: This parameter doesn't do anything. It is used as a quick fix to allow repeats in the sequencer
	repeat = IntegerParameter('Repeat', group_by='scanType', group_condition=' ', default=0)


	# Defines what data will be emitted for the main window
	DATA_COLUMNS = ['Delay', 'X', 'Y', 'SigMon', 'Freq', 'FFT']

	saveOnShutdown = False

	# Keeps track of when the measurement was started
	startTime = None

	def startup(self):
		# Main dictionary to store data
		self.data = {'Delay': [], 'X':[], 'Y':[], 'SigMon': [], 'Freq':[], 'FFT':[]}

		self.startTime = datetime.now()
		self.dacRange = ULRange.BIP10VOLTS
		log.info("Startup")

		if self.scanType != 'Read DAC':
			# Try and connect to XPS
			try:
				if self.xps == None:
					log.info("Connecting to XPS")
					self.xps = xpsHelp.InitXPS(self.xpsIP)
				else:
					log.info("XPS already connected")

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
		
		log.info("Estimated end time = {}".format(str(self.estimateEndTime().strftime("%H:%M:%S"))))
	
	def executeReadDAC(self):
		# Counter used to track progress
		counter = 0

		# Read lockin until stop command is given
		while(True):
			if self.should_stop():
				break

			# Wait 2 time constants
			waitTime = self.dacWait * 2

			self.data['Delay'].append(counter * waitTime)

			# Take measurement from DAC
			# NOTE: May need to convert to enginerring units to get voltage
			self.data['X'].append(self.lockinSen * ul.to_eng_units(self.mccdacBoard, self.dacRange, ul.a_in(self.mccdacBoard, self.mccdacXChannel, self.dacRange)) / 10) # Convert to mV
			self.data['Y'].append(self.lockinSen * ul.to_eng_units(self.mccdacBoard, self.dacRange, ul.a_in(self.mccdacBoard, self.mccdacYChannel, self.dacRange)) / 10) # Convert to mV

			# Wait
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
		tc = self.dacWait

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

			# Take measurement from DAC
			self.data['X'].append(self.lockinSen * ul.to_eng_units(self.mccdacBoard, self.dacRange, ul.a_in(self.mccdacBoard, self.mccdacXChannel, self.dacRange)) / 10) # Convert to lockin mV
			self.data['Y'].append(self.lockinSen * ul.to_eng_units(self.mccdacBoard, self.dacRange, ul.a_in(self.mccdacBoard, self.mccdacYChannel, self.dacRange)) / 10) # Convert to mV


			curData = {'Delay': self.data["Delay"][counter], 'X': self.data["X"][counter], 'Y': self.data["Y"][counter]}

			# Emit data
			self.emit('results', curData)

			# Update progress
			self.emit('progress', ((counter + 1) / len(delayPoints)) * 100)

			counter += 1

	def execute(self):
		if self.scanType == 'Step Scan':
			self.saveOnShutdown = True
			self.executeStepScan()
			self.emitFFT()

		elif self.scanType == 'Goto Delay':
			self.executeGotoDelay()

		elif self.scanType == 'Read DAC':
			self.saveOnShutdown = True
			self.executeReadDAC()

		# Log measurement time
		self.endTime = datetime.now()

		measurementTime = self.endTime - self.startTime

		log.info("Measurement Time: {:.3f} min".format(measurementTime / timedelta(minutes=1)))
	
	# Should be called by the main window program
	# Assigns the path to the current temporary file
	def setTempFile(self, tempFilePath):
		self.curTempFile = tempFilePath

	# Should be called by the main window program
	# Assigns the default save path
	def setDefaultDir(self, path):
		self.defaultDir = path

	def emitFFT(self):
		# FFT the data stored in 'self.data'
		freq, fftX = GetFFTAbs(self.data['Delay'], self.data['X'])

		# Store the FFT to the data dictionary
		self.data['Freq'] = freq
		self.data['FFT'] = fftX

		# Emit the FFT data
		for i in range(len(freq)):
			curData = {'Freq': freq[i], 'FFT': fftX[i]}
			self.emit('results', curData)

	def pymeasureSave(self, savepath):
		# Copy the current temp file to the savepath
		shutil.copy(self.curTempFile, savepath)

	def joshSave(self, savepath):
		# Create savefile
		with open(savepath, 'w') as datFile:
			writer = csv.writer(datFile, delimiter='\t', lineterminator='\n')
			
			# Write headers
			writer.writerow(['Delay', 'X', 'Y', 'FFT Freq', 'FFT', 'SigMon']) # Headers
			writer.writerow(['ps', 'mV', 'mV', 'THz', 'amp', 'V']) # Units

			# Write data
			for i in range(len(self.data['Delay'])):
				curDelay = str(self.data['Delay'][i])
				curX = str(self.data['X'][i])
				curY = str(self.data['Y'][i])

				try:
					curFreq = str(self.data['Freq'][i])
				except:
					curFreq = "NaN"

				try:
					curFFT = str(self.data['FFT'][i])
				except:
					curFFT = "NaN"

				try:
					curSigMon = str(self.data['SigMon'][i])
				except:
					curSigMon = "NaN"

				writer.writerow([curDelay, curX, curY, curFreq, curFFT, curSigMon])


		# Save pymeasure file to settings folder
		curFolder = os.path.dirname(savepath)
		settingsSavepath = os.path.join(curFolder, "settings")

		# Check if settings folder exists
		if not os.path.exists(settingsSavepath):
			# Create settings folder
			os.mkdir(settingsSavepath)
		
		# Create the full path to save the pymeasure file
		settingsSavepath = os.path.join(settingsSavepath, os.path.basename(savepath) + ".pym")

		self.pymeasureSave(settingsSavepath)

		
	def trySaveFile(self):
		# Checks if the flag 'saveOnShutdown' is enabled
		# This flag should be set if needed for the given scan type in 'execute()'
		if self.saveOnShutdown:
			# Check if the file is to be named without bringing up a dialog
			if self.autoFileNameControl:
				fileCount = 1

				autoNameBase = self.autoFileBaseName

				if autoNameBase == " ":
					autoNameBase = ""

				# Add to the base auto file name if instrument control has been selected
				# XPS 2
				if self.xps2Control:
					autoNameBase = "{}_delay={}ps".format(autoNameBase, self.xps2Delay)

				# Get the full path of the auto-named file
				autoFilePath = os.path.join(self.defaultDir, autoNameBase)

				curSavePath = autoFilePath + ".dat"

				# Check if the file exists
				# If it does, append number to end and increment
				while os.path.exists(curSavePath):
					fileCount += 1
					curSavePath = autoFilePath + "_{}".format(fileCount) + ".dat"

				# Build the complete filepath
				savepath = curSavePath
			else:
				# Bring up a save dialog
				savepath = ChooseSaveFile()
			
			# Check that a file was selected
			if savepath != '':
				log.info("Saving data to " + savepath)
				
				# Check what format to save the file as
				if self.outputFormat == 'pymeasure':
					self.pymeasureSave(savepath)
				elif self.outputFormat == 'Josh File':
					self.joshSave(savepath)

			# No file selected
			else:
				log.info("Data not saved")

	def estimateEndTime(self):
		curStartTime = datetime.now()

		if self.scanType == 'Step Scan':
			duration = ((self.stopDelay - self.startDelay) / self.stepDelay) * self.dacWait * 2.0


		elif self.scanType == 'Goto Delay' or self.scanType == 'Read DAC':
			duration = 0
		
		return (curStartTime + timedelta(seconds=duration))

	# Should be called by the main window program
	# Assigns the XPS object to the program
	# This is done to prevent crashes when running many consecutive scans
	def setXPS(self, xps):
		self.xps = xps

	def shutdown(self):
		self.trySaveFile()
		self.xps = None
	
