# TDSpy
Python code to run TDS experiments

## Experiment Setup Instructions
1. Connect electronics
   1. DC Power Supply (+-15V) -> Photodiode Power Input
   2. Photodiode output -> Transimpedence amplifier
   3. Transimpedence amplifier -> Lockin A
   4. Lockin CH1 Output (X) -> DAC CH 0
   5. Lockin CH2 Output (Y) -> DAC CH 1
   6. DAC USB -> PC
   7. Amplifier Ref (3 kHz) -> ThorLabs Chopper Ext Input
   8. ThorLabs Chopper Ref Output (1.5 kHz) -> Sig Gen Ext Trig In
   9. ThorLabs Chopper Ref Output (1.5 kHz) -> Lockin Ref In
   10. Sig Gen CH 1 Out (20V Peak-Peak Max) -> PCA Emitter
   11. XPS Ethernet Switch -> PC
2.  Set up ThorLabs Chopper
    1.  Ref Out -> Target
    2.  Frequency multiplier -> 1 / 2
3. Set up Sig Gen
   1. Set CH 1 output voltage
   2. Set Modulation -> Burst Mode
   3. Frequency -> 1.51 kHz (real frequency output will be 1.5 kHz, forces output pulse to end before next trigger)
4.  Run InstaCal
5.  Run 'TDSpy.py'
    1.  Select 'Step Scan'
    2.  Input scan parameters (lockin time constant and sensitivity must be inputted manually)
    3.  Press 'Queue' to acquire TDS scan
6.  For repeat measurements:
    1.  Click 'Add root item' in 'Sequencer' (bottom left of program)
    2.  Change 'Parameter' to 'Repeat'
    3.  In 'Sequence' input 'arange(1, repeats+1, 1)' (e.g. for 10 repeats, input  'arange(1, 11, 1)')
    4.  Select 'Auto Name File' tick box
    5.  Input base file name (e.g. "Emitter_5V_97mW") (Repeat no. automatically appended to file name)
    6.  Select directory to save files to (press the Folder icon in 'Directory' and select folder with GUI)
    7.  Press 'Queue Sequence'