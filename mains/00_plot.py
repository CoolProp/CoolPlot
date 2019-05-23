
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from CoolPlot.Plot import PropertyPlot
plot = PropertyPlot('R290', 'ph')
plot.calc_isolines()
plot.show()
