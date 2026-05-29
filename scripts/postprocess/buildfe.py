

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

import tempfile

import morphopt
import torch
import importlib.util
import matplotlib.pyplot as plt

torch.set_default_dtype(torch.float64)
torch.set_default_device('cuda:0')

def readhistoryparams(path_result: str, iteration: int = -1):
    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)


    Controller: morphopt.Controller = MAIN_SCRIPT_FOR_RESTART.ThisController

    controller: morphopt.Controller = Controller()

    controller._load_history(path_result=path_result, target_iteration=iteration)

    
    with tempfile.TemporaryDirectory(prefix='morphopt_') as tmpdir:
        fe = controller.params.create_feamodel(tmpdir + '/')

    return fe


if __name__ == "__main__":

    fe = readhistoryparams('d:/Work/results/locomotion/FRONT_T20260421_190912_YCX/', iteration=124)
    fe.assembly._loads['P_s1'].pressure = 0.08
    fe.assembly._loads['P_s2'].pressure = 0.08
    fe.assembly._loads['P_s3'].pressure = 0.08
    result = fe.solve()
    import pyvista as pv

    mesh = fe.assembly.get_instance('final_model').surfaces.get_trimesh('surface_0_All')

    nodes = fe.assembly.get_instance('final_model').nodes
    displacement = fe.assembly._GC2RGC(result.GC)[0]

    
    import numpy as np

    ins = fe.assembly.get_instance('final_model')
    nodes = ins.nodes.detach().cpu().numpy()
    displacement = fe.assembly._GC2RGC(result.GC)[ins._RGC_index].detach().cpu().numpy()
    deformed_nodes = nodes + displacement
    displacement_magnitude = np.linalg.norm(displacement, axis=1)

    faces = np.hstack([
        np.full((mesh.shape[0], 1), 3, dtype=np.int64),
        mesh.detach().cpu().numpy().astype(np.int64)
    ]).ravel()
    pv_mesh = pv.PolyData(deformed_nodes, faces)
    pv_mesh["U"] = displacement_magnitude

    plotter = pv.Plotter(window_size=(1400, 900))
    plotter.set_background('white')
    plotter.add_mesh(
        pv_mesh,
        scalars="U",
        cmap="jet",
        show_edges=False,
        smooth_shading=True,
        lighting=True,
        scalar_bar_args={
            'title': 'Displacement',
            'title_font_size': 14,
            'label_font_size': 12,
            'vertical': True,
        },
    )
    
    plotter.add_axes(line_width=1, color='black')
    plotter.enable_lightkit()
    plotter.view_isometric()
    plotter.show(title='Abaqus-style displacement plot')

    raise NotImplementedError
