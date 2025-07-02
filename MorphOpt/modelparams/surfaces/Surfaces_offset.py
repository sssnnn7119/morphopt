from .Surfaces import Surfaces

class Surfaces_offset(Surfaces):
    """
    The Surfaces_offset class is a subclass of Surfaces that represents surfaces with an offset.
    It initializes the surfaces with a specified thickness and maximum step length.
    """

    def __init__(self, thickness: float, max_step_length: list[float], *args, **kwargs) -> None:
        super().__init__(max_step_length=max_step_length, *args, **kwargs)
        
        self.thickness = thickness
        """
        The thickness of the surfaces' shell.
        """

        
    def export_data(self, filepath) -> list[str]:
        name = []
        for i in range(self.num_surface):
            surf_name0 = '__surface-%d' % i
            name_now = self.surface_list[i].output_data(path_output=filepath, name_output=surf_name0, flip=(i!=0))
            name.append(name_now)

        return name