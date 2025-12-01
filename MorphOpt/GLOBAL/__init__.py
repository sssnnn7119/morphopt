"""
For the MorphOpt package, this module contains the parameters for the optimization process.
It includes classes for defining the parameters for the Finite Element Method (FEM) analysis, the optimization process, and the recording of the optimization history.
"""

from .History import History as __History
from .Path import Path as __Path
from .fearults import ObjectiveFunction

PATH = __Path()
History = __History()
obj_fun: ObjectiveFunction = None

from ..opt_loop import Controller as __Controller

controller: __Controller = None