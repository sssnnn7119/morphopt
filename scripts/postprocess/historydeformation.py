if __name__ == "__main__":
    import pyvista as pv
    import math
    from pathlib import Path

    import torchfea
    import torch
    import numpy as np
    ext_inp = torchfea.FEA_INP()
    ext_inp.read_inp('A:/MineData/Learning/Code/Projects/MorphOpt/examples/tmech2025contact/grasp/obj.inp')
    fe = torchfea.from_inp(ext_inp)
    fe.assembly.initialize()
    inst = fe.assembly.get_instance('obj')
    trans = [-3., 0., -5.]
    inst._translation = torch.tensor(trans)

    exmesh = fe.assembly.get_instance('obj').get_mesh(surf_name='contact')

    # Output folder must exist; create it if missing
    out_dir = Path('Z:/temp')
    out_dir.mkdir(parents=True, exist_ok=True)

    plotter = pv.Plotter(off_screen=True, window_size=[2500, 2500])
    plotter.open_gif(str(out_dir / 'deform.gif'))
    plotter.show(auto_close=False)

    num_frame = 60
    for titer in range(num_frame):
        iteration = 1 + int(294 * titer / num_frame)

        mesh = pv.read('A:/MineData/Learning/Publications/TMECH2025Contact/results/Optimization/grasp/result/GRASP_T20260302_163335/log/deformation/task_0_iter_%d.obj' % iteration)

        plotter.clear()

        plotter.add_mesh(mesh, color=(40.0 / 255, 120.0 / 255, 181.0 / 255), show_edges=True)
        plotter.add_mesh(exmesh, color='lightgray', show_edges=True)
        
        plotter.remove_all_lights()
        plotter.add_light(pv.Light(light_type='headlight', intensity=0.8))  # Mayavi 默认: 跟随相机的头灯

        if titer == 0:
            plotter.enable_parallel_projection()
            azimuth = 90
            elevation = 0
            plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                math.sin(math.radians(elevation))))

        plotter.screenshot(str(out_dir / f'deform{titer:03d}.png'))
        plotter.write_frame()

    plotter.close()