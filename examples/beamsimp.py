
import morphopt
import torch
mumax = 10.
minratio = 1e-7

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='/run/media/song/缓存/results/', 
                         opt_label='BeamMinEnergy')
        
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
            energy = self.fe.assembly.get_instance('final_model').potential_energy(RGC=RGC)

            return -self.fe_results[0].GC[-4]

        def get_metrics(self):
            RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)
            energy = self.fe.assembly.get_instance('final_model').potential_energy(RGC=RGC)
            return [-self.fe_results[0].GC[-4], energy, self.get_volume_fraction()]

    class Params(morphopt.simp.Params):
        class GeometryParams(morphopt.simp.FixedGeometryINP):

            def __init__(self):

                super().__init__(mesh_file="/run/media/song/SS/MineData/Learning/Publications/RAL2026FEA/results/case1beamsimp/model/beamsimp.inp")

        class FEAParams(morphopt.simp.FEAParams):

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='fix', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 20., 0.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='loadedge'))

                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='allset', index_dof=[0]))

                self.add_fea_interface(self.ConcentratedForceInterface(rp_name='RP_head'), name='force_1')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=0), name='penalty_rp_head_translation_x')
                # self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=2), name='penalty_rp_head_translation_z')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=4), name='penalty_rp_head_rotation_y')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RP_head', s=5), name='penalty_rp_head_rotation_z')

            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(0, "force_1", [0., 0., -2e-1])
                self.set_step_params(0, "penalty_rp_head_translation_x", [1e6, 0.0])
                # self.set_step_params(0, "penalty_rp_head_translation_z", [1e2, 10.0])
                self.set_step_params(0, "penalty_rp_head_rotation_y", [1e6, 0.0])
                self.set_step_params(0, "penalty_rp_head_rotation_z", [1e6, 0.0])

        class MaterialParams(morphopt.simp.SIMP_BSPFieldMaterials):
            
            def __init__(self):
                super().__init__(mumax=mumax, 
                                 kappamax=mumax*10, 
                                 density=1.08e-9, 
                                 initial_ratio=2.,
                                 simp_ratio_min=minratio, 
                                 bounding_box=[-0.5, 0.5, -20, 20, -0, 10], 
                                 simp_field_resolution=0.5, 
                                 degree=2,
                                 voidpenalfactor=0e-4,
                                 elementname='C3D8')
            def get_meshes(self):
                xmin, xmax, ymin, ymax, zmin, zmax = self._bounding_box
                nx, ny, nz = self._bsp_size
                import numpy as np
                import pyvista as pv
                # Sample at the BSP control-point resolution × 2 for smooth rendering
                nx_q = 1
                ny_q = max(2, (ny - 1) * 2 + 1)
                nz_q = max(2, (nz - 1) * 2 + 1)

                xq = np.array([0.])  # Only one point in x direction since it's a beam
                yq = np.linspace(ymin, ymax, ny_q)
                zq = np.linspace(zmin, zmax, nz_q)
                xg, yg, zg = np.meshgrid(xq, yq, zq, indexing="ij")
                pts_query = np.stack([xg, yg, zg], axis=-1).reshape(-1, 3)

                designfield = self._map_bsp_designfield(
                    torch.from_numpy(pts_query).to(torch.get_default_device()).to(torch.get_default_dtype())
                )
                ratio_query = self.get_material_ratio(designfield).reshape(nx_q, ny_q, nz_q).cpu().numpy()
                ratio_grid = np.clip(ratio_query, 0.0, 1.0)

                spacing = (
                    (xmax - xmin) / max(nx_q - 1, 1),
                    (ymax - ymin) / max(ny_q - 1, 1),
                    (zmax - zmin) / max(nz_q - 1, 1),
                )
                grid = pv.ImageData(
                    dimensions=(nx_q, ny_q, nz_q),
                    spacing=spacing,
                    origin=(xmin, ymin, zmin),
                )
                grid.point_data["density"] = ratio_grid.flatten(order="F")

                return [grid]
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(morphopt.simp.SIMPSolver):
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
                             device='cpu',
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

                self.add_constraints(self.objectivefuncs.VolFrac(volfrac_min=0.4, volfrac_max=0.6, penalty=1e6, element_name='C3D8'))

                self.if_update = True
    
if __name__ == '__main__':

    morphopt.start_optimization(device='cpu', restart_per_iteration=10)
