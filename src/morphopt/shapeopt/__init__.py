"""Concrete interfaces used for boundary-surface shape updates.

The common optimization model lives directly in :mod:`morphopt`: compose
``GeometryParams``, ``FEAParams``, ``MaterialsParams``, ``Solver`` and
``Updaters`` there.  This package only owns the concrete boundary Part
interface and the updater that knows how to update it.
"""

from .boundarypartinterface import BoundaryPartInterface
from .update_boundarypart import UpdaterBoundaryPart

__all__ = ["BoundaryPartInterface", "UpdaterBoundaryPart"]
