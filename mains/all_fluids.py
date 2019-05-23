import CoolProp
from CoolProp.Plots import PropertyPlot

fluids = CoolProp.CoolProp.FluidsList()

for i, fluid in enumerate(fluids):
    plot = PropertyPlot('R290', 'ph')
    plot.calc_isolines()
    plot.show()

    if i > 3:
        break
        