import torch


def show_quiver3d(R, N, hold=False):
    from mayavi import mlab
    r = R.detach().cpu().numpy()
    n = N.detach().cpu().numpy()
    mlab.quiver3d(r[0], r[1], r[2], n[0], n[1], n[2])

    if not hold:
        mlab.show()
    
def show_mesh_normal(r, coo, hold=False, color=None):
    normal = torch.cross(r[:, coo[:, 1]] - r[:, coo[:, 0]],
                         r[:, coo[:, 2]] - r[:, coo[:, 0]], dim=0)
    normal = normal / normal.norm(dim=0)
    
    r_mid = (r[:, coo[:, 0]] + r[:, coo[:, 1]] + r[:, coo[:, 2]]) / 3
    from mayavi import mlab
    r = r_mid.tolist()
    coo = coo.tolist()
    if color is None:
        mlab.quiver3d(r[0], r[1], r[2], normal[0], normal[1], normal[2])
    else:
        mlab.quiver3d(r[0],
                      r[1],
                      r[2],
                      normal[0],
                      normal[1],
                      normal[2],
                      color=color)
    if not hold:
        mlab.show()

def show_surf(r, coo, hold=False, color=None):
    r = r.tolist()
    coo = coo.tolist()
    from mayavi import mlab
    if color is None:
        mlab.triangular_mesh(r[0], r[1], r[2], coo, opacity=1)
    else:
        mlab.triangular_mesh(r[0],
                             r[1],
                             r[2],
                             coo,
                             opacity=1,
                             color=color)
    surface = mlab.pipeline.surface(mlab.pipeline.triangular_mesh_source(
        r[0], r[1], r[2], coo),
                                    color=(1.0 / 255, 1.0 / 255, 1.0 / 255),
                                    opacity=1)
    surface.actor.property.representation = 'wireframe'

    if not hold:
        mlab.show()


def show_surf2(r,
               coo,
               hold=False,
               color=(232.0 / 255, 232.0 / 255, 232.0 / 255),
               if_points=False):

    r0 = r.clone()[:, coo.unique()]

    r2 = torch.zeros_like(r[0]).tolist()
    r = r.tolist()
    coo = coo.tolist()
    from mayavi import mlab
    mlab.triangular_mesh(r[0], r[1], r2, coo, opacity=1, color=color)
    surface = mlab.pipeline.surface(mlab.pipeline.triangular_mesh_source(
        r[0], r[1], r2, coo),
                                    color=(1.0 / 255, 1.0 / 255, 1.0 / 255),
                                    opacity=1)
    surface.actor.property.representation = 'wireframe'

    if if_points:

        mlab.points3d(r0[0],
                      r0[1],
                      torch.zeros_like(r0[0]).tolist(),
                      scale_factor=0.04,
                      color=(40.0 / 255, 120.0 / 255, 181.0 / 255))

    if not hold:
        mlab.show()


def show_plot(data):
    from matplotlib import pyplot as plt
    d = data.detach().cpu().numpy()
    plt.plot(d)


def show_points(r, hold=False, scale_factor=0.1, color=(1, 0, 0)):
    from mayavi import mlab
    r = r.tolist()
    mlab.points3d(r[0], r[1], r[2], scale_factor=scale_factor, color=color)
    if not hold:
        mlab.show()


def show_points2(r, hold=False, scale_factor=0.1, color=(1, 0, 0)):
    from mayavi import mlab
    r2 = torch.zeros_like(r[0]).tolist()
    r = r.tolist()
    mlab.points3d(r[0], r[1], r2, scale_factor=scale_factor, color=color)
    if not hold:
        mlab.show()
