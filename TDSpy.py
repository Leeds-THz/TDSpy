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


####################################################################
# THz Procedure
####################################################################

class THzProcedure(Procedure):
	startV = IntegerParameter('Start Step', units='ps', default=2)
	endV = IntegerParameter('End Step', units='ps', default=100)
	StepSize = FloatParameter('Step Size', units='ps', default=0.1)
	WaitTime = FloatParameter('Wait Time', units='s', default=0.2)
	Sensitivity=FloatParameter('Sensitivity', units='A', default=5E-10)
	
	DATA_COLUMNS = ['Time Delay', 'THz Amplitude']


	def startup(self):
		log.info("Startup")

	def execute(self):
		log.info("Executing")

####################################################################
# Main Window
####################################################################

class MainWindow(ManagedWindow):
	def __init__(self):
		super().__init__(
			procedure_class=THzProcedure,
			inputs=['startV','endV','StepSize','WaitTime','Sensitivity'],
			displays=['startV','endV','StepSize','WaitTime','Sensitivity'],
			x_axis='Time Delay',
			y_axis='THz Amplitude'
		#     try:
		#         sequencer=True,                                      # Added line
		#         sequencer_inputs=['startV', 'endV', 'StepSize'],    # Added line
		#         sequence_file="gui_sequencer_example_sequence.txt",  # Added line, optional
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
