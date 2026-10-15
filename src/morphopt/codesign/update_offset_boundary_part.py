"""Geometry updates for one cavity offset Part."""

from ..shapeopt.update_boundary_part import UpdaterBoundaryPart
from ..shapeopt import objectivefuncs as shape_objectivefuncs
from .offset_boundary_part import OffsetBoundaryPart
from .constraints import InwardCurvatureRadius, OffsetSurfaceMinThickness


class UpdaterOffsetBoundaryPart(UpdaterBoundaryPart):
    """Reuse shape updates, binding only to an OffsetBoundaryPart.

    Register with ``add_geometry_updater(self.Offset(), name="body")``.
    Offset layer positions follow the Part's surface variables automatically.
    """

    target_type = OffsetBoundaryPart

    class objectivefuncs:
        """Shape objectives and constraints for cavity offset geometry."""

        ShapeDerivative = shape_objectivefuncs.ShapeDerivative
        Fairness = shape_objectivefuncs.Fairness
        Distance = shape_objectivefuncs.Distance
        VolumeMaximization = shape_objectivefuncs.VolumeMaximization
        boundarys = shape_objectivefuncs.boundarys
        BaseObjective = shape_objectivefuncs.BaseObjective
        BaseConstraints = shape_objectivefuncs.BaseConstraints
        InwardCurvatureRadius = InwardCurvatureRadius
        OffsetSurfaceMinThickness = OffsetSurfaceMinThickness
