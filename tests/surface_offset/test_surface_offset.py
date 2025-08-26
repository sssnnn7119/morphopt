import torch
import os
import sys

sys.path.append(os.getcwd())
os.environ['CUDA_LAUNCH_BLOCKING'] = '1'
os.environ['KMP_DUPLICATE_LIB_OK']='True'
from MorphOpt.modelparams.surfaces.SurfaceInterface.CPGEOSphereInterface import CPGEOSurfaceInterface
torch.set_default_dtype(torch.float64)
torch.set_default_device('cuda:0')
import CPGEO
def get_offseted_surface(surface: CPGEOSurfaceInterface, init_coordinates: torch.Tensor):
    # Create a new surface by offsetting the original surface
    offset_surface = surface.clone()
    offset_surface.offset(init_coordinates)
    return offset_surface


def get_offseted_points(surface: CPGEOSurfaceInterface, coordinates: torch.Tensor, thickness: float):

    r, rdu = surface.model.map_c(points=coordinates, derivative=1)
    normal = torch.cross(rdu[:, 0, :], rdu[:, 1, :], dim=0)
    normal = normal / torch.norm(normal, dim=0)
    return r + thickness * normal

def get_triangle_normals(points: torch.Tensor, connection: torch.Tensor):
    # Calculate normals for each triangle in the mesh
    p0 = points[:, connection[:, 0]]
    p1 = points[:, connection[:, 1]]
    p2 = points[:, connection[:, 2]]
    v1 = p1 - p0
    v2 = p2 - p0
    normals = torch.cross(v1, v2, dim=0)
    normals_length = torch.norm(normals, dim=0)
    normals = normals / normals_length
    return normals

geo0 = CPGEOSurfaceInterface.initialize_Cylinder(seed_size=0.1, flip=False, r0=1.0, init_location=[0, 0, 0], length=2.0)
geo0.load("Tests/surface_offset/Surface-1_iter-97")

# points0, connection = geo0.model.uniformly_mesh(seed_size=1.)
points0 = geo0.model.knots.clone()
connection = geo0.model.cp_elements.clone()
edges = CPGEO.surface._mesh_methods.get_edges(connection)

grids_0 = geo0.model.reference_to_curvilinear(points0)
grid_new = torch.nn.Parameter(torch.randn([2, points0.shape[1]]) * 1e-5)

with torch.no_grad():
    points_offset_0 = get_offseted_points(geo0, grids_0.detach(), thickness=1.5)
alpha = 0.1

r_0 = geo0.model.map_c(points=grids_0, derivative=1)[0]
normal_tri_0 = get_triangle_normals(r_0, connection)

opt = torch.optim.LBFGS(params=[grid_new], max_iter=40, line_search_fn='strong_wolfe', lr=1, tolerance_grad=1e-15, tolerance_change=1e-15)

def closure():
    opt.zero_grad()
    points_offset = get_offseted_points(geo0, grids_0 + grid_new, thickness=1.5)
    loss_distance = alpha *((points_offset - points_offset_0)**2).sum() + \
            ((points_offset[:, edges[:, 0]] - points_offset[:, edges[:, 1]])**2).sum()
    
    normal_tri = get_triangle_normals(points_offset, connection)
    loss_normal = -((normal_tri * normal_tri_0).sum(dim=0)).sum()
    loss = loss_distance + loss_normal * 0

    loss.backward()
    return loss

for i in range(3):
    loss = opt.step(closure)

    print(f"Iteration {i}, Loss: {loss.item()}")

from mayavi import mlab
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
    
points_offset = get_offseted_points(geo0, grids_0 + grid_new, thickness=1.5)
show_surf(points_offset.cpu().numpy(), connection)
points_offset_0[2] += 30
show_surf(points_offset_0.cpu().numpy(), connection)

mlab.show()

# Removed NotImplementedError to allow script to finish without error.
raise NotImplementedError("Surface offsetting not implemented yet.")

