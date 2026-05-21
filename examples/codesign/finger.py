

import cpgeo.utils
from numpy import ma
import torchfea

import morphopt
import torch
import cpgeo
import numpy as np
mumax = 4.82
minratio = 1e-6

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results/', 
                         opt_label='Twist_Energy')
        
    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()

            self.second_step = False

        def reinitialize(self, *args, **kwargs):
            super().reinitialize(*args, **kwargs)

            if morphopt.controller.history.iteration > 50:
                if np.abs(morphopt.controller.history.history_objective[-1] / np.mean(morphopt.controller.history.history_objective[-15:])) > 0.9:
                    self.second_step = True
                    print("Switching to second step with energy-based objective.")

        def get_volume_fraction(self):
            elems = self.fe.assembly._parts['final_model'].elems['C3D4']

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


            assembly = self.fe.assembly
            RGC0 = assembly._GC2RGC(self.fe_results[0].GC)
            RGC1 = assembly._GC2RGC(self.fe_results[1].GC)

            E0 = assembly._total_Potential_Energy(RGC=RGC0)
            E1 = assembly._total_Potential_Energy(RGC=RGC1)

            elems: torchfea.elements.C3D4 = assembly.get_part('final_model').elems['C3D4']

            energy_density = elems.get_potential_energy_density(U=RGC1[0])
            gaussian_weight = elems.gaussian_weight
            gaussian_points = elems.get_gaussian_points(nodes=assembly.get_instance('final_model').nodes)

            loss_work = E1 - E0
            V = gaussian_weight.sum()
            avg_density = (energy_density * gaussian_weight).sum() / V

            t = 10
            p = 2

            matpara: morphopt.codesign.CodesignMaterials = morphopt.controller.params.materials
            ratio = matpara._map_bsp_designfield(nodes=gaussian_points.reshape(-1, 3)).flatten()

            penalty = (gaussian_weight.flatten() * (torch.clamp(energy_density / avg_density - t, min=0).flatten() * ratio) ** p)

            ratio = 1e-7 if self.second_step else 0.

            return loss_work + penalty.sum() * ratio

        def get_metrics(self):

            assembly = self.fe.assembly
            RGC0 = assembly._GC2RGC(self.fe_results[0].GC)
            RGC1 = assembly._GC2RGC(self.fe_results[1].GC)
            E0 = assembly._total_Potential_Energy(RGC=RGC0)
            E1 = assembly._total_Potential_Energy(RGC=RGC1)

            elems: torchfea.elements.C3D4 = assembly.get_part('final_model').elems['C3D4']

            energy_density = elems.get_potential_energy_density(U=RGC1[0])
            gaussian_weight = elems.gaussian_weight
            gaussian_points = elems.get_gaussian_points(nodes=assembly.get_instance('final_model').nodes)

            loss_work = E1 - E0
            V = gaussian_weight.sum()
            avg_density = (energy_density * gaussian_weight).sum() / V
            t = 10
            p = 2

            matpara: morphopt.codesign.CodesignMaterials = morphopt.controller.params.materials
            ratio = matpara._map_bsp_designfield(nodes=gaussian_points.reshape(-1, 3)).flatten()

            penalty = (gaussian_weight.flatten() * (torch.clamp(energy_density / avg_density - t, min=0).flatten() * ratio) ** p)


            return [self.fe_results[1].GC[-1],
                    E0, E1, penalty.sum(),
                    self.get_volume_fraction()]

    class Params(morphopt.Params):

        class GeometryParams(morphopt.codesign.CodesignGeometry):
            class CPGEO_Symmetry(morphopt.GeometryParams.CPGEO):

                def reinitialize(self):
                    super().reinitialize()
                    
                    result = cpgeo.utils.enforce_rotational_symmetry_z(
                            vertices=self._cps.detach().cpu().numpy(),
                            faces=self.model._cp_faces,
                            periods=3
                        )
                    self._cps = torch.from_numpy(result[0]).to(self._cps.device)
                    self.model._cp_faces = result[1]
                    self.model._control_points = result[0]
                    self.model.initialize()
                    self.pre_load()
                    return self

            def __init__(self):

                super().__init__(fea_seed_size=2.5, 
                                 reinitialize_per_iter=10,
                                 thickness=2.5,
                                 num_layers=1,
                                 mesh_order=2)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=12.,
                                                    length=80.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    flip=False, maxR=0.1, maxC=1.0, maxFF=0.2))
 
                self.add_surface(
                    self.CPGEO_Twist.initialize_Sphere(seed_size=1.5,
                                                flip=True,
                                                r0=8.,
                                                init_location=[0., 0., 60.],
                                                MaxC=1.5,
                    ))
                
                self.add_surface(
                    self.CPGEO_Twist.initialize_Sphere(seed_size=1.5,
                                                flip=True,
                                                r0=8.,
                                                init_location=[0., 0., 20.],
                                                MaxC=1.5,
                    ))
                    

            def _symmetry_constraint(self, P0: torch.Tensor):
                P0_ = P0.reshape([2, -1, 3])
                P0_[1, :, 0] = -P0_[1, :, 0]
                P0_[1, :, 1] = P0_[1, :, 1]
                P0_[1, :, 2] = P0_[1, :, 2]
                return P0_.reshape([-1, 3])

            def apply_surface_constraints(self):
                self.surface_list[1]._cps = self._symmetry_constraint(self.surface_list[1]._cps)
                self.surface_list[2]._cps = self._symmetry_constraint(self.surface_list[2]._cps)

        class FEAParams(morphopt.codesign.CodesignFEAParams):
                
            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_offset'),
                                        name='pressure_1')
                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_2_offset'),
                                        name='pressure_2')

            def define_steps(self):
                self.set_step_num(2)
                self.set_step_params(0, "pressure_1", [0.06])

                self.set_step_params(1, "pressure_1", [0.06])

        class MaterialParams(morphopt.codesign.CodesignMaterials):
            
            def __init__(self):
                super().__init__(mumax=mumax, 
                                 kappamax=mumax * 10, 
                                 density=1.08e-9, 
                                 simp_ratio_min=minratio, 
                                 initial_ratio=0.5,
                                 bounding_box=[-25, 25, -25, 25, 0, 50], 
                                 simp_field_resolution=1.0, 
                                 degree=3,
                                 shell_mu=0.48,
                                 shell_kappa=4.8,
                                 shell_density=1.08e-9,
                                 voidpenalfactor=1e-1,
                                 densitypenal=3,)
        
            def _map_bsp_designfield(self, nodes):
                theta120 = 2.0 * torch.pi / 3.0
                theta240 = 4.0 * torch.pi / 3.0

                c120 = torch.cos(torch.tensor(theta120, device=nodes.device, dtype=nodes.dtype))
                s120 = torch.sin(torch.tensor(theta120, device=nodes.device, dtype=nodes.dtype))
                c240 = torch.cos(torch.tensor(theta240, device=nodes.device, dtype=nodes.dtype))
                s240 = torch.sin(torch.tensor(theta240, device=nodes.device, dtype=nodes.dtype))

                # 0 deg
                nodes_rot0 = nodes
                # +120 deg around z
                nodes_rot120 = torch.stack([
                    c120 * nodes[:, 0] - s120 * nodes[:, 1],
                    s120 * nodes[:, 0] + c120 * nodes[:, 1],
                    nodes[:, 2],
                ], dim=1)
                # +240 deg around z
                nodes_rot240 = torch.stack([
                    c240 * nodes[:, 0] - s240 * nodes[:, 1],
                    s240 * nodes[:, 0] + c240 * nodes[:, 1],
                    nodes[:, 2],
                ], dim=1)

                ratio0 = super()._map_bsp_designfield(nodes_rot0)
                ratio120 = super()._map_bsp_designfield(nodes_rot120)
                ratio240 = super()._map_bsp_designfield(nodes_rot240)

                return (ratio0 + ratio120 + ratio240) / 3.0
            
            def _map_bsp_designfield_with_spartial_derivative(self, nodes):
                theta120 = 2.0 * torch.pi / 3.0
                theta240 = 4.0 * torch.pi / 3.0

                c120 = torch.cos(torch.tensor(theta120, device=nodes.device, dtype=nodes.dtype))
                s120 = torch.sin(torch.tensor(theta120, device=nodes.device, dtype=nodes.dtype))
                c240 = torch.cos(torch.tensor(theta240, device=nodes.device, dtype=nodes.dtype))
                s240 = torch.sin(torch.tensor(theta240, device=nodes.device, dtype=nodes.dtype))

                # 0 deg
                nodes_rot0 = nodes
                # +120 deg around z
                nodes_rot120 = torch.stack([
                    c120 * nodes[:, 0] - s120 * nodes[:, 1],
                    s120 * nodes[:, 0] + c120 * nodes[:, 1],
                    nodes[:, 2],
                ], dim=1)
                # +240 deg around z
                nodes_rot240 = torch.stack([
                    c240 * nodes[:, 0] - s240 * nodes[:, 1],
                    s240 * nodes[:, 0] + c240 * nodes[:, 1],
                    nodes[:, 2],
                ], dim=1)

                ratio0 = super()._map_bsp_designfield_with_spartial_derivative(nodes_rot0)
                ratio120 = super()._map_bsp_designfield_with_spartial_derivative(nodes_rot120)
                ratio240 = super()._map_bsp_designfield_with_spartial_derivative(nodes_rot240)

                return (ratio0 + ratio120 + ratio240) / 3.0

        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(morphopt.MorphSolver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.Params):

            super().__init__(params=params,
                            num_process=1,
                            task_index_list=[[0, 1]],
                            available_gpus=['cuda:0'],)

    class Updater(morphopt.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: morphopt.Params, *args, **kwargs):
            super().__init__(surfaces=self.UpdaterGeometries(params=params),
                            materials=self.UpdaterMaterials(params=params),
                            *args, **kwargs)
        class UpdaterGeometries(morphopt.UpdaterGeometries):
            """
            Updater class for morphopt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self, params: morphopt.Params):

                super().__init__(
                    params=params,
                    max_step_iter=100)
                
                shape_derivative = self.objectivefuncs.ShapeDerivative()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[0.0, 0.0],
                                                                [0.0, 2.5]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=17., height=47., bottom=3.))
                
                self.add_constraints(morphopt.codesign.InwardCurvatureRadius(geometry=params.geometry))
                self.add_constraints(morphopt.codesign.OffsetSurfaceMinThickness(geometry=params.geometry, min_distance=2.0))

                self.if_update = [False, True]

        class UpdaterMaterials(morphopt.UpdaterMaterials):
            """
            Material updater based on SIMP control points.
            """

            def __init__(self, params: morphopt.Params):
                super().__init__(
                    params=params,
                    max_step_iter=200,
                    max_step_length=0.1,
                )

                shape_derivative = self.objectivefuncs.Sensitivity(normalize_gradient=False)
                self.add_objective_function(shape_derivative)

                density_regularization = self.objectivefuncs.DensityFieldMinimize(scale=1e-8)
                self.add_objective_function(density_regularization)

                # Keep SIMP control points within [0, 1] and avoid singular material values.
                self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=0.001, threshold=0.0, p=2))
                self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=0.999, threshold=0.0, p=2))

                self.if_update = True
    
if __name__ == '__main__':

    morphopt.start_optimization(device='cpu', restart_per_iteration=50)
