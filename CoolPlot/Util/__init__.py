# -*- coding: utf-8 -*-

import CoolProp

def is_string(in_obj):
    try:
        return isinstance(in_obj, basestring)
    except NameError:
        return isinstance(in_obj, str)
    # except:
    #    return False

def _get_index(prop):
    if is_string(prop):
        return CoolProp.CoolProp.get_parameter_index(prop)
    elif isinstance(prop, int):
        return prop
    else:
        raise ValueError("Invalid input, expected a string or an int, not {0:s}.".format(str(prop)))