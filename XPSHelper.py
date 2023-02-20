####################################################################
# IMPORTS
####################################################################
import os
from newportxps import NewportXPS
import math
import csv
import numpy as np

####################################################################
# UNIT FUNCTIONS
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

####################################################################
# GENERAL FUNCTIONS
####################################################################

def InitXPS(ip, user = "Administrator", password = "Administrator"):
	os.system("ssh-keyscan {} > {}\\.ssh\\known_hosts.".format(ip, os.path.expanduser('~')))

	xps = NewportXPS(ip, username=user, password=password)

	return xps

####################################################################
# GATHERING FUNCTIONS
####################################################################

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
# STEP SCAN FUNCTIONS
####################################################################

def InitXPSStepScan(xps, stage, startDelay, stepDelay, stopDelay, zeroOffset, passes, reverse):
	# Get max velocity settings
	maxVeloAcc = xps._xps.PositionerMaximumVelocityAndAccelerationGet(xps._sid, stage)

	# Set velocity to max
	err, msg = xps._xps.PositionerSGammaParametersSet(xps._sid, stage, maxVeloAcc[1], maxVeloAcc[2], 0.005, 0.05)

	# Check for errors
	if err != 0:
		return err, msg

	# Move stage to start pos
	xps.move_stage(stage, ConvertPsToMm(startDelay, zeroOffset, passes, reverse))

	return err, msg
