
from math import e

import torchfea

import morphopt
import torch
mumax = 10.
minratio = 1e-7

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='/run/media/song/缓存/results/', 
                         opt_label='Spring')
        
    class ObjectiveFunction(morphopt.simp.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def get_volume_fraction(self):
            elems = self.fe.assembly._parts['final_model'].elems['C3D8']

            materials = elems.materials

            mu = materials['material-0']._mu
            gaussian_weight = elems.gaussian_weight  # [gaussian, element]

            ratio_now = (mu - mumax * minratio) / (mumax * (1 - minratio))
            ratio_now = ratio_now.clamp(0.0, 1.0)

            volume = gaussian_weight * ratio_now
            volume_total = gaussian_weight.sum()

            volume_fraction = volume.sum() / volume_total

            return volume_fraction

        def objective_function(self):


            RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)

            elems: torchfea.elements.C3D8 = self.fe.assembly.get_part('final_model').elems['C3D8']

            energy_density = elems.get_potential_energy_density(U = RGC[0])
            gaussian_weight = elems.gaussian_weight

            energy = (energy_density * gaussian_weight).sum()

            return -energy

        def get_metrics(self):
            RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)
            energy = self.fe.assembly.get_instance('final_model').potential_energy(RGC=RGC)
            return [-self.fe_results[0].GC[-4], energy, self.get_volume_fraction()]

    class Params(morphopt.simp.Params):
        class GeometryParams(morphopt.simp.FixedGeometryINP):

            def __init__(self):

                super().__init__(mesh_file="/run/media/song/SS/MineData/Learning/Publications/RAL2026FEA/results/case2spring/model/beamsimp.inp")

        class FEAParams(morphopt.simp.FEAParams):

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='fix', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 40.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='loadedge'))

                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=0), name='force_x')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=1), name='force_y')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=2), name='force_z')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=3), name='force_rx')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=4), name='force_ry')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=5), name='force_rz')
            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(0, "force_x", [1e4, 0])
                self.set_step_params(0, "force_y", [1e4, 0])
                self.set_step_params(0, "force_z", [1e2, 10e0])
                self.set_step_params(0, "force_rx", [1e4, 0])
                self.set_step_params(0, "force_ry", [1e4, 0])
                self.set_step_params(0, "force_rz", [1e4, 0])

        class MaterialParams(morphopt.simp.SIMP_BSPFieldMaterials):
            
            def __init__(self):
                super().__init__(mumax=4.82, 
                                 kappamax=48, 
                                 density=1.08e-9, 
                                 simp_ratio_min=minratio, 
                                 bounding_box=[-10, 10, -10, 10, -0, 40], 
                                 simp_field_resolution=1.0, 
                                 degree=2,
                                 voidpenalfactor=1e-4,
                                 initial_ratio=-1,
                                 elementname='C3D8')
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(morphopt.simp.Solver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.simp.Params):

            super().__init__(params=params,
                             available_gpus=['cuda:0'],
                            num_process=1)

    class Updater(morphopt.simp.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: morphopt.simp.Params, *args, **kwargs):
            super().__init__(materials=self.UpdaterMaterials(params=params),
                            *args, **kwargs)

        class UpdaterMaterials(morphopt.simp.UpdaterMaterials):
            """
            Material updater based on SIMP control points.
            """

            def __init__(self, params: morphopt.simp.Params):
                super().__init__(
                    params=params,
                    max_step_iter=100,
                )

                shape_derivative = self.objectivefuncs.Sensitivity(normalize_gradient=False)
                self.add_objective_function(shape_derivative)

                # density_regularization = self.objectivefuncs.DensityFieldMinimize(scale=1e-7)
                # self.add_objective_function(density_regularization)

                # Keep SIMP control points within [0, 1] and avoid singular material values.
                self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=-15, threshold=0.0, p=2))
                self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=15, threshold=0.0, p=2))

                self.add_constraints(self.objectivefuncs.VolFrac(volfrac_min=0.3, volfrac_max=0.6, penalty=1e6, element_name='C3D8'))

                self.if_update = True
    
if __name__ == '__main__':

    morphopt.start_optimization(device='cpu', restart_per_iteration=10)
