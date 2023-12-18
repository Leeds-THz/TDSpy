####################################################################
# PACKAGES REQUIRED
####################################################################

# pymeasure
# newportxps
# matplotlib
# PyQt5
# pywin32
# scipy

####################################################################
# IMPORTS
####################################################################
import logging
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

import XPSHelper as xpsHelp
import TDSProcedure as tdsProc
from pymeasure.log import console_log
from pymeasure.display.Qt import QtWidgets
from pymeasure.display.windows import ManagedWindow
# from pymeasure.display.windows.managed_dock_window import ManagedDockWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import BooleanParameter, IntegerParameter, FloatParameter, Parameter, ListParameter
import tempfile
import sys
import shutil
import os
from pymeasure.log import console_log

####################################################################
# Main Window
####################################################################

# class TDSWindow(ManagedDockWindow):
class TDSWindow(ManagedWindow):
	def __init__(self):
		super().__init__(
			procedure_class=tdsProc.TDSProcedure,
			inputs=['scanType','startDelay','stepDelay','stopDelay', 'gotoDelay', 'thzBandwidth','xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse', 'xps2Control', 'xps2Stage', 'xps2Passes', 'xps2ZeroOffset', 'xps2Reverse', 'xps2Delay', 'mccdacBoard','mccdacXChannel','mccdacYChannel','dacWait', 'lockinSen', 'autoFileNameControl', 'autoFileBaseName', 'outputFormat', 'repeat'],
			displays=['scanType','startDelay','stepDelay','stopDelay', 'gotoDelay', 'thzBandwidth','xpsIP','xpsStage','xpsPasses','xpsZeroOffset','xpsReverse', 'xps2Control', 'xps2Stage', 'xps2Passes', 'xps2ZeroOffset', 'xps2Reverse', 'xps2Delay','mccdacBoard','mccdacXChannel','mccdacYChannel','dacWait', 'lockinSen' ],
			x_axis='Delay',
			y_axis='X',
			sequencer=True,
            sequencer_inputs=['startDelay', 'stepDelay', 'stopDelay', 'xps2Delay', 'repeat'],
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

		self.xps = None

	def queue(self, procedure=None):
		# Connect to XPS if unconnected
		if self.xps == None:
			try:
				self.xps = xpsHelp.InitXPS(self.inputs.xpsIP.parameter.value)
			except:
				log.warning("Could not perform initial XPS connection")

		# Create temp file to save data to
		curTempFile = tempfile.mktemp(dir=self.tempDir)

		if procedure is None:
			procedure = self.make_procedure()
		
		# Pass the name of the current temporary file to the procedure
		procedure.setTempFile(curTempFile)

		# Pass the default directory to the procedure
		procedure.setDefaultDir(self.directory)

		# Pass the XPS instance
		procedure.setXPS(self.xps)

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
