import os
import sys

import FEA
import numpy as np
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import GLOBAL
from MorphOpt.opt_loop import Controller as _Controller
from MorphOpt.modelparams import Surfaces, Loads, Materials
from MorphOpt import initializer
from MorphOpt import solvers
from MorphOpt.updaters.surface import update_surfaces
from MorphOpt.updaters.updaters import Updaters
from MorphOpt import generatemodel
from MorphOpt.modelparams import Params as _Params

class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self, U, Udp, UdF, *args, **kwargs):
        loss1 = -U[0, -2]
        # loss2 = -U[1, 2]
        # loss3 = (UdF**2).sum() / 200000
        return loss1
GLOBAL.obj_fun = ObjectiveFunction()

class Params(_Params):
    class SurfaceParams(Surfaces):

        def __init__(self):

            super().__init__(max_step_length=[0.4, 0.4, 0.4, 0.4])

            self.add_surface(
                Surfaces.BSP.initialize_cylinder(r0=10.,
                                                        length=80.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        flip=False, maxR=0.1, maxC=0.7, maxFF=0.2, perturbation_L=12.))
            
            self.add_surface(
            Surfaces.BSP.initialize_cylinder(r0=4.,
                                                    length=74.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[0, 0, 3],
                                                    flip=True, maxR=0.1, maxC=0.7, maxFF=0.2, perturbation_L=12.))
        
            
            
            self.if_update = [True, True]
            
    class LoadParams(Loads):
        class _Pressure(Loads.Pressures):
            def __init__(self):
                super().__init__()
                self.pressure = torch.Tensor([[0.06]])
        
        def __init__(self):
            self.pressure = self._Pressure()
            
    class MaterialParams(Materials):
        
        def __init__(self):
            super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
    
    def __init__(self):
        super().__init__(surfaces=self.SurfaceParams(), loads=self.LoadParams(), materials=self.MaterialParams())

class Generator(generatemodel.Genetrator):
    def __init__(self, surfaces: Surfaces, path_output: str = None, path_queue: str = None) -> None:
        """
        Initialize the Genetrator class.
        
        Parameters:
            surfaces (Surfaces): The surfaces of the soft robot.
            path_output (str): The path to the output directory.
            path_queue (str): The path to the queue directory.
        """
        super().__init__(seed_size=1.2, surfaces=surfaces, path_output=path_output, path_queue=path_queue)

class Solver(solvers.Morph):
    """
    Solver class for MorphOpt.
    This class is responsible for solving the finite element analysis (FEA) problem.
    """

    def __init__(self, params: Params):

        super().__init__(params=params,
                         num_process=1)
        
    @staticmethod
    def init_FEA(inp: FEA.FEA_INP) -> FEA.FEAController:
        """
        Initialize the FEA class with the given input parameters.

        Parameters:
            inp (FEA.FEA_INP): The input parameters for the FEA class.

        Returns:
            FEA.FEAController: An instance of the FEA_Main class with the given input parameters.
            
        """
        inp_cylinder = FEA.FEA_INP()
        inp_cylinder.Read_INP("C:/Users/24391/Documents/MineData/Learning/Code/Projects/MorphOpt/Jobs/ral2025contact/cylinder.inp")
        fe_cylinder = FEA.from_inp(inp_cylinder)
        part_cylinder = fe_cylinder.assembly.get_part('cylinder')

        fe = FEA.from_inp(inp)
        fe.assembly.add_part(part_cylinder, name='cylinder')
        fe.assembly.add_instance(FEA.Instance(part=part_cylinder), name='cylinder')

        fe.solver = FEA.solver.StaticImplicitSolver()
        ins_name = 'final_model'
        ins = fe.assembly.get_instance(ins_name)
        ins_cylinder = fe.assembly.get_instance('cylinder')
        # convert to the second order elements
        # fe = FEA.elements.convert_to_second_order(fe, ['element-0'])
        ins_cylinder._translation = torch.tensor([-1,0,-10.])
        
        # add contact between cylinder and model
        fe.assembly.add_load(FEA.loads.Contact(instance_name1=ins_name, instance_name2='cylinder', 
                                                surface_name1='surface_0_All', surface_name2='contact'))
        
        # boundary condition on cylinder
        fe.assembly.add_constraint(FEA.constraints.Boundary_Condition(instance_name='cylinder', index_nodes=np.arange(0, ins_cylinder.nodes.shape[0])))

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
        fe.assembly.add_constraint(FEA.constraints.Boundary_Condition(instance_name=ins_name, index_nodes=bc_dof),
                        name='BC')        # add reference point and constraints
        
        
        rp = FEA.ReferencePoint([0., 0., ins.nodes[:, 2].max()],)
        rp_name = fe.assembly.add_reference_point(rp=rp)
        indexNodes = inp.part['final_model'].sets_nodes['surface_0_Head']
        fe.assembly.add_constraint(FEA.constraints.Couple(instance_name=ins_name, indexNodes=indexNodes, rp_name=rp_name)
        )

        
        return fe
 

class Updater(Updaters):
    """
    Updater class for MorphOpt.
    This class is responsible for updating the design variables based on the results of the optimization process.
    """

    def __init__(self, params: Params, *args, **kwargs):
        super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                         loads=None, *args, **kwargs)

    class UpdaterSurfaces(update_surfaces.UpdaterSurfaces):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(
                params=params,
                max_step_iter=100)

            shape_derivative = update_surfaces.objectivefuncs.ShapeDerivativeDirect()
            self.add_objective_function(shape_derivative)
            self.add_objective_function(
                update_surfaces.objectivefuncs.Fairness(surfaces=params.surfaces, sensitivity=shape_derivative))
            self.add_objective_function(
                update_surfaces.objectivefuncs.Distance(min_distance=
                                                            [[2.5, 2.5],
                                                             [2.5, 2.5]]))
            self.add_objective_function(
                update_surfaces.objectivefuncs.boundarys.Cylinder(radius=12., height=80., bottom=0.))
    
class Controller(_Controller):
    pass
    
if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')

    path_result = 'Z:/Results'
    opt_label = 'FRONT'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()
    
    generator = Generator(surfaces=params.surfaces,path_output=GLOBAL.PATH.path_Result + '/Cache/', path_queue=GLOBAL.PATH.path_Queue)

    solver = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, generator=generator, solver=solver, updater=updater)
    controller.opt_loop()
