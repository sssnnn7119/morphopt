from ..base_params import BaseParams

class BaseGeometry(BaseParams):
    """
    Base class for geometry parameter classes.

    Subclasses must provide the mesh/geometry generation and assembly modification
    behavior used by the optimization pipeline.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)

    def generate(self, path_result: str, pools=None):
        """Generate the FEA part for the current geometry."""
        raise NotImplementedError
    
