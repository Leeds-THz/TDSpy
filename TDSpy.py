####################################################################
# PACKAGES REQUIRED
####################################################################

# pythonnet
# pymeasure
# matplotlib
# newportxps
# PyQt5

####################################################################
# IMPORTS
####################################################################
import logging
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())
import clr
import os
import sys
import tempfile
import random
from time import sleep
from pymeasure.log import console_log
from pymeasure.display.Qt import QtWidgets
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import IntegerParameter, FloatParameter, Parameter
import numpy as np
import matplotlib.pyplot as plt
from pymeasure.instruments.signalrecovery import DSP7265
from newportxps import NewportXPS


####################################################################
# THz Procedure
####################################################################

class THzProcedure(Procedure):
	startV = IntegerParameter('Start Step', units='ps', default=2)
	endV = IntegerParameter('End Step', units='ps', default=100)
	StepSize = FloatParameter('Step Size', units='ps', default=0.1)

	LockinGPIB = IntegerParameter('Lockin GPIB', units='', default=12)
	WaitTime = FloatParameter('Wait Time', units='s', default=0.1)
	Sensitivity=FloatParameter('Sensitivity', units='mV', default=100e-3)
	
	DATA_COLUMNS = ['Time Delay', 'X', 'Y']


	def startup(self):
		log.info("Startup")

		# Try and connect to Lock-In
		try:
			# Connect to the given GPIB port
			self.lockin = DSP7265("GPIB::{}".format(self.LockinGPIB))
			sleep(0.1)

			# Set time constant
			log.info("Setting the Time Constant to %s A" % self.WaitTime)
			self.lockin.time_constant=self.WaitTime
			sleep(0.1)

			# Set sensitivity
			log.info("Setting the sensitivity to %s A" % self.Sensitivity)
			self.lockin.sensitivity=self.Sensitivity
			sleep(0.1)

		except Exception as e:
			log.info("Lockin initialisation failed")
			log.info(str(e))
			log.info(str(e.args))
		

	def execute(self):
		log.info("Executing")

		for i in range(10):
			data = {'Time Delay': i, 'X': self.lockin.x, 'Y': self.lockin.y}
			self.emit('results', data)

			if self.should_stop():
				log.warning("Caught the stop flag in the procedure")
				break

			sleep(1)


####################################################################
# Main Window
####################################################################

class MainWindow(ManagedWindow):
	def __init__(self):
		super().__init__(
			procedure_class=THzProcedure,
			inputs=['startV','endV','StepSize', 'LockinGPIB', 'WaitTime','Sensitivity'],
			displays=['startV','endV','StepSize', 'LockinGPIB', 'WaitTime','Sensitivity'],
			x_axis='Time Delay',
			y_axis='X'
			# y_axis=['X', 'Y']
			)
		self.setWindowTitle('THz Scan')

	def queue(self):
		filename = tempfile.mktemp()

		procedure = self.make_procedure()
		results = Results(procedure, filename)
		experiment = self.new_experiment(results)

		self.manager.queue(experiment)


####################################################################
# Main
####################################################################

if __name__ == "__main__":
	app = QtWidgets.QApplication(sys.argv)
	window = MainWindow()
	window.show()
	sys.exit(app.exec())
