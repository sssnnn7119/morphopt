import os

import torchfea
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

import numpy as np
from torchfea import inp

import morphopt
import torch
import importlib.util
import matplotlib.pyplot as plt

torch.set_default_dtype(torch.float64)
torch.set_default_device('cuda')


def readhistoryparams(path_result: str, iteration: int = -1) -> morphopt.Params:
    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)


    Controller: morphopt.Controller = MAIN_SCRIPT_FOR_RESTART.ThisController

    controller: morphopt.Controller = Controller()

    controller._load_history(path_result=path_result, target_iteration=iteration)


    return controller

if __name__ == "__main__":


    path_result = 'Z:/Results/Twist_Energy_T20260518_094234/'
    
    controller: morphopt.Controller = readhistoryparams(path_result, 130)

    fe = controller.params.create_feamodel()
    fe.initialize()

    controller.params.feamodel.process_fea(fe=fe, step_index=1)

    # result: torchfea.solver.StaticResult = fe.solve()
    U = fe.assembly._GC2RGC(fe.assembly.GC)[0]

    elems: torchfea.elements.Element_3D = fe.assembly.get_instance('final_model').elems['C3D4']

    gaussian_nodes = elems.get_gaussian_points(nodes=fe.assembly.get_instance('final_model').nodes).reshape(-1, 3)
    strain_energy = elems.get_potential_energy_density(U=U).flatten()

    mu = list(elems.materials.values())[0]._mu.flatten()


    import pyvista as pv

    points = np.asarray(gaussian_nodes.detach().cpu()) if torch.is_tensor(gaussian_nodes) else np.asarray(gaussian_nodes)
    energy = np.asarray(strain_energy.detach().cpu()).ravel() if torch.is_tensor(strain_energy) else np.asarray(strain_energy).ravel()
    mu_values = np.asarray(mu.detach().cpu()).ravel() if torch.is_tensor(mu) else np.asarray(mu).ravel()

    cloud = pv.PolyData(points)
    cloud['strain_energy'] = energy
    cloud['mu'] = mu_values

    # glyphs = cloud.glyph(
    #     geom=pv.Sphere(radius=1.0),
    #     scale='mu',
    #     orient=False,
    #     factor=0.5,
    # )

    plotter = pv.Plotter()
    # plotter.add_mesh(
    #     glyphs,
    #     scalars='strain_energy',
    #     cmap='viridis',
    #     scalar_bar_args={'title': 'Strain Energy'}
    # )


    controller.params.geometry.plot(plotter=plotter)
    controller.params.materials.plot(plotter=plotter)


    plotter.show()

    raise NotImplementedError()