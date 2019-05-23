.. _Humid-Air:

Humid Air Properties
********************

.. contents:: :depth: 2

Examples
--------

.. jupyter-execute::

  name = 'world'
  print('hello ' + name + '!')


.. jupyter-execute::

  import numpy as np
  from matplotlib import pyplot
  %matplotlib inline

  x = np.linspace(0, 2 * np.pi)

  pyplot.plot(x, np.sin(x) / x)
  pyplot.plot(x, np.cos(x))
  pyplot.grid()



Psychrometric Chart
-------------------

.. plot::

    import numpy as np
    import CoolProp.CoolProp as CP
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1,1,figsize=(10, 8))
    Tdbvec = np.linspace(-30, 55)+273.15

    # Lines of constant relative humidity
    for RH in np.arange(0.1, 1, 0.1):
        W = CP.HAPropsSI("W","R",RH,"P",101325,"T",Tdbvec)
        plt.plot(Tdbvec-273.15, W, color='k', lw = 0.5)

    # Saturation curve
    W = CP.HAPropsSI("W","R",1,"P",101325,"T",Tdbvec)
    plt.plot(Tdbvec-273.15, W, color='k', lw=1.5)

    # Lines of constant Vda
    for Vda in np.arange(0.69, 0.961, 0.01):
        R = np.linspace(0,1)
        W = CP.HAPropsSI("W","R",R,"P",101325,"Vda",Vda)
        Tdb = CP.HAPropsSI("Tdb","R",R,"P",101325,"Vda",Vda)
        plt.plot(Tdb-273.15, W, color='b', lw=1.5 if abs(Vda % 0.05) < 0.001 else 0.5)

    # Lines of constant wetbulb
    for Twb_C in np.arange(-16, 33, 2):
        if Twb_C == 0:
            continue
        R = np.linspace(0.0, 1)
        print(Twb_C)
        Tdb = CP.HAPropsSI("Tdb","R",R,"P",101325,"Twb",Twb_C+273.15)
        W = CP.HAPropsSI("W","R",R,"P",101325,"Tdb",Tdb)
        plt.plot(Tdb-273.15, W, color='r', lw=1.5 if abs(Twb_C % 10) < 0.001 else 0.5)

    plt.xlabel(r'Dry bulb temperature $T_{\rm db}$ ($^{\circ}$ C)')
    plt.ylabel(r'Humidity Ratio $W$ (kg/kg)')
    plt.ylim(0, 0.030)
    plt.xlim(-30, 55)
    # plt.show()
