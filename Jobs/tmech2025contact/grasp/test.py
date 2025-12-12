import os
os.environ['KMP_DUPLICATE_LIB_OK']='True'
import torch

import FEA
import multiprocessing as mp
import numpy as np

def init_FEA(inp: FEA.FEA_INP) -> FEA.FEAController:
    """
    Initialize the FEA class with the given input parameters.

    Parameters:
        inp (FEA.FEA_INP): The input parameters for the FEA class.

    Returns:
        FEA.FEAController: An instance of the FEA_Main class with the given input parameters.
        
    """
    inp_cylinder = FEA.FEA_INP()
    inp_cylinder.read_inp("C:/Users/24391/Documents/MineData/Learning/Code/Projects/MorphOpt/Jobs/tmech2025contact/grasp/rec.inp")
    fe_cylinder = FEA.from_inp(inp_cylinder)
    part_cylinder = fe_cylinder.assembly.get_part('rec')

    fe = FEA.from_inp(inp)
    fe.assembly.add_part(part_cylinder, name='rec')
    fe.assembly.add_instance(FEA.Instance(part=part_cylinder), name='rec')

    fe.solver = FEA.solver.StaticImplicitSolver()
    ins_name = 'final_model'
    ins = fe.assembly.get_instance(ins_name)
    ins_cylinder = fe.assembly.get_instance('rec')
    # convert to the second order elements
    # fe = FEA.elements.convert_to_second_order(fe, ['element-0'])
    ins_cylinder._translation = torch.tensor([10,0,50.])
    
    # add contact between cylinder and model
    fe.assembly.add_load(FEA.loads.Contact(instance_name1=ins_name, instance_name2='rec', 
                                            surface_name1='surface_0_All', surface_name2='contact'),)
    
    # boundary condition on cylinder
    fe.assembly.add_boundary(FEA.boundarys.Boundary_Condition(instance_name='rec', set_nodes_name='contact'))

    # add loads
    i=0
    while True:
        if 'surface_%d_All' % (i + 1) not in ins.surfaces.keys():
            break
        fe.assembly.add_load(FEA.loads.Pressure(instance_name=ins_name, surface_set='surface_%d_All' % (i + 1), pressure=0.),
                    name='Pressure_%d' % i)
        i += 1
    
    # add contact self
    i = 0
    while True:
        if 'surface_%d_All' % (i) not in ins.surfaces.keys():
            break
        fe.assembly.add_load(FEA.loads.ContactSelf(instance_name=ins_name, surface_name='surface_%d_All' % (i)),
                    name='ContactSelf_%d' % i)
        i += 1

    # add boundary condition
    bc_dof = inp.part['final_model'].sets_nodes['surface_0_Bottom']
    fe.assembly.add_boundary(FEA.boundarys.Boundary_Condition(instance_name=ins_name, set_nodes_name='surface_0_Bottom'),
                    name='BC')        # add reference point and constraints
    
    
    rp = FEA.ReferencePoint([0., 0., ins.nodes[:, 2].max()],)
    rp_name = fe.assembly.add_reference_point(rp=rp)
    indexNodes = inp.part['final_model'].sets_nodes['surface_0_Head']
    fe.assembly.add_constraint(FEA.constraints.Couple(instance_name=ins_name, set_nodes_name='surface_0_Head', rp_name=rp_name)
    )

    
    return fe


import os
os.environ['KMP_DUPLICATE_LIB_OK']='True'
import sys
import torch
sys.path.append(os.getcwd())
import FEA

current_process_name = mp.current_process().name
try:
    pool_id = int(current_process_name.split("-")[-1]) % 4
except:
    pool_id = 0



torch.set_default_device(torch.device('cuda'))
torch.set_default_dtype(torch.float64)
torch.cuda.empty_cache()
# construct the FEA
FE_inp = FEA.FEA_INP()
FE_inp.read_inp('Z:/Results/GRASP_T20251204_202644/FEA/TopOptRun.inp')

fe = init_FEA(FE_inp)

# change the load
fe.assembly._loads['Pressure_%d' % 0].pressure = 0.08

# solve displacement 0
fe.solver.maximum_iteration = 100000
result = fe.solve(tol_error=1e-4)

# if not result:
#     raise RuntimeError(
#         "FEA solver failed to converge. Please check the input parameters."
#     )

GC0 = fe.assembly.GC.clone().detach()

print(GC0[-6:].tolist())

assembly = fe.assembly
R = assembly._assemble_generalized_Matrix(GC=GC0.to(assembly.device))[0]
R_now = R[assembly.RGC_list_indexStart[assembly.get_instance('rec')._RGC_index]:assembly.RGC_list_indexStart[assembly.get_instance('rec')._RGC_index+1]].reshape([-1, 3])
Rf = R_now.sum(dim=0)

# extern_surf = fe.loads['pressure-1'].surface_element.cpu().numpy()
ins1 = fe.assembly.get_instance('final_model')
ins2 = fe.assembly.get_instance('rec')
extern_surf = ins1.surfaces.get_elements('surface_0_All')[0]._elems.cpu().numpy()
extern_surf2 = ins2.surfaces.get_elements('contact')[0]._elems.cpu().numpy()
# extern_surf = fem.part['final_model'].surfaces['surface_1_All']

from mayavi import mlab
import vtk
from mayavi import mlab
coo=extern_surf

# Get the deformed surface coordinates
U1 = fe.assembly.RGC[ins1._RGC_index].cpu().numpy()
U2 = fe.assembly.RGC[ins2._RGC_index].cpu().numpy()
undeformed_surface1 = ins1.nodes.cpu().numpy()
undeformed_surface2 = ins2.nodes.cpu().numpy()
deformed_surface1 = undeformed_surface1 + U1
deformed_surface2 = undeformed_surface2 + U2

r1=deformed_surface1.transpose()
r2=deformed_surface2.transpose()

Unorm1 = (U1**2).sum(axis=1)**0.5
Unorm2 = (U2**2).sum(axis=1)**0.5

# surface = mlab.pipeline.triangular_mesh_source(r[0], r[1], r[2], coo)
# surface_vtk = surface.outputs[0]._vtk_obj
# stlWriter = vtk.vtkSTLWriter()
# stlWriter.SetFileName('test.stl')
# stlWriter.SetInputConnection(surface_vtk.GetOutputPort())
# stlWriter.Write()
# mlab.close()

# Plot the deformed surface
mesh1=mlab.triangular_mesh(deformed_surface1[:, 0], deformed_surface1[:, 1], deformed_surface1[:, 2], extern_surf, scalars=Unorm1)
mesh2=mlab.triangular_mesh(deformed_surface2[:, 0], deformed_surface2[:, 1], deformed_surface2[:, 2], extern_surf2[:, [0,1,2]], scalars=Unorm2)

mesh1.actor.property.edge_visibility = True
mesh1.actor.property.line_width = 1.0
mesh1.actor.property.edge_color = (0, 0, 0)  # Black edges

mesh2.actor.property.edge_visibility = True
mesh2.actor.property.line_width = 1.0
mesh2.actor.property.edge_color = (0, 0, 0)  # Black edges

if extern_surf2.shape[1] > 3:
    mesh3=mlab.triangular_mesh(deformed_surface2[:, 0], deformed_surface2[:, 1], deformed_surface2[:, 2], extern_surf2[:, [0,2,3]], scalars=Unorm2)
    mesh3.actor.property.edge_visibility = True
    mesh3.actor.property.line_width = 1.0
    mesh3.actor.property.edge_color = (0, 0, 0)  # Black edges

mlab.show()