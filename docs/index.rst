.. You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to CoolPlot's documentation!
====================================

Contents:

.. toctree::
   :maxdepth: 2

   HumidAir



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`



Mixture Syntax
==============

You can also specify mixtures straight away and pass the mole fractions as part of the 
fluid string. 

.. plot::
    :include-source:   

    import matplotlib.pyplot as plt
    from CoolPlot.Plot.Plots import PropertyPlot
    fig = plt.figure()
    plot = PropertyPlot("REFPROP::ISOBUTAN[0.8]&PROPANE[0.2]", 'PH', unit_system='EUR', tp_limits='ACHP', figure=fig)
    plot.calc_isolines()
    plot.show()

If you would like to specify the mass fractions instead, you have to construct the state
object separately and pass it to the plot object instead of a string.

.. plot::
    :include-source:   

    import CoolProp
    state = CoolProp.AbstractState("REFPROP", "ISOBUTAN&PROPANE")
    state.set_mass_fractions([0.8,0.2])
    import matplotlib.pyplot as plt
    from CoolPlot.Plot.Plots import PropertyPlot
    fig = plt.figure()
    plot = PropertyPlot(state, 'TS', unit_system='EUR', tp_limits='ACHP', figure=fig)
    plot.calc_isolines()
    plot.show()

