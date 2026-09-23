"""Geometry parameter collection: an ordered list of Part interfaces.

``GeometryParams`` is the geometry counterpart of ``MaterialsParams`` and
``FEAParams``: a user model registers one *part interface* per Part, and each
interface owns that Part together with the Instances that place it.  This
collection deliberately knows nothing about surfaces — boundary-parameterised
geometry (the shape-optimization
:class:`morphopt.shapeopt.BoundaryPartInterface`) adds that concept on top of
the part interface, and the geometry updater binds to *it*.

```python
class GeometryParams(morphopt.GeometryParams):
    def define_interface(self) -> None:
        self.add_interface(self.INPPartInterface("rec.inp"), name="block")
```
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torchfea

from .baseparam import BaseParams

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

__all__ = ["GeometryParams"]


class GeometryParams(BaseParams):
    """Ordered list of named Part interfaces (Parts plus their Instances)."""

    from .partinterface import (
        BasePartInterface,
        INPPartInterface,
        TorchFEAPartInterface,
    )

    def instance_names(self) -> list[str]:
        """Instance names produced by the registered interfaces."""
        return [
            name
            for interface in self.interfaces.values()
            for name in interface.instance_names
        ]

    # -------------------------------------------------------------- lifecycle
    def pathlog_required(self) -> list[str]:
        return ["geometry"]

    # --------------------------------------------------------------- assembly
    def generate(self, path_result: str, pools: Pool | None = None) -> torchfea.Assembly:
        """Build the assembly holding every interface's Parts and Instances."""
        assembly = torchfea.Assembly()
        for interface in self.interfaces.values():
            interface.add_to_assembly(assembly, path_result=path_result, pools=pools)
        return assembly

    def export_data(self, foldpath: str) -> None:
        """Export the geometry description of every interface."""
        for interface in self.interfaces.values():
            interface.export_data(interface.workdir(foldpath))
