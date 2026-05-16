from .material import CodesignMaterials
from .geometry import CodesignGeometry
from .constraints import InwardCurvatureRadius, OffsetSurfaceMinThickness
from .feaparams import CodesignFEAParams




def plot_geometry_and_materials(geometry: CodesignGeometry, materials: CodesignMaterials):
    import pyvista as pv
    plotter = pv.Plotter(window_size=(1400, 900))
    plotter.set_background('white')

    plotter = materials.plot(plotter=plotter)
    geometry.plot(plotter=plotter, opacity=[0.0, 1.0])

    plotter.show()