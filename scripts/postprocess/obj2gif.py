import math

import pyvista as pv

if __name__ == "__main__":
    plotter = pv.Plotter(off_screen=True, window_size=[2500, 2500])
    plotter.open_gif('Z:/temp/deform.gif')
    plotter.show(auto_close=False)
    # plotter.remove_all_lights()
    # plotter.add_light(pv.Light(light_type='headlight', intensity=0.8))  # Mayavi 默认: 跟随相机的头灯

    num_frame = 21
    for titer in range(num_frame):
        iteration = titer

        mesh = pv.read('Z:/temp/model_%d.obj' % iteration)
        cymesh = pv.read('Z:/temp/contact_cylinder.obj')
        plotter.clear()

        plotter.add_mesh(mesh, color=(40.0 / 255, 120.0 / 255, 181.0 / 255), show_edges=True)
        plotter.add_mesh(cymesh, color='lightgray', show_edges=True)
        


        if titer == 0:

            plotter.enable_parallel_projection()
            azimuth = 90
            elevation = 0
            plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
                math.sin(math.radians(elevation))))
        plotter.screenshot('Z:/temp/deform%d.png' % titer)
        plotter.write_frame()
    plotter.close()