
import morphopt
import torch
mumax = 4.82
minratio = 0.000001

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results/', 
                         opt_label='EXAMPLE')
        
    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()

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
            RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)
            energy = self.fe.assembly.get_instance('final_model').potential_energy(RGC=RGC)
            vol_frac = self.get_volume_fraction()
            return -energy + (vol_frac - 0.4) ** 2

        def get_metrics(self):
            RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)
            energy = self.fe.assembly.get_instance('final_model').potential_energy(RGC=RGC)
            return [energy, self.get_volume_fraction()]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.shapeopt.GeometryParams):

            def __init__(self):

                super().__init__(fea_seed_size=1.2, 
                                 reinitialize_per_iter=5,
                                 thickness=1.5,
                                 num_layers=2,)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=15.,
                                                    length=80.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    flip=False, maxR=0.1, maxC=1.0, maxFF=0.2))
                
            def apply_surface_constraints(self) -> None:
                """
                Apply the constraints (e.g. the symmetric constraint) of the surfaces.
                """
                a: ThisController.Params.GeometryParams.BSP = self.surface_list[0]
                cp0 = a._cps.reshape(a.model.size[0], a.model.size[1], 3)
                import torch
                cp0[:, :, 0] = (cp0[:, :, 0] + torch.flip(cp0[:, :, 0], dims=[1])) / 2
                cp0[:, :, 1] = (cp0[:, :, 1] - torch.flip(cp0[:, :, 1], dims=[1])) / 2
                cp0[:, :, 2] = (cp0[:, :, 2] + torch.flip(cp0[:, :, 2], dims=[1])) / 2


        class FEAParams(morphopt.FEAParams):

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                self.add_fea_interface(self.ConcentratedForceInterface(rp_name='RP_head'), name='force_1')

            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(0, "force_1", [1., 0., -0.])
                

        class MaterialParams(morphopt.simp.SIMPMaterials):
            
            def __init__(self):
                super().__init__(mumax=4.82, 
                                 kappamax=48, 
                                 density=1.08e-9, 
                                 simp_ratio_min=minratio, 
                                 bounding_box=[-20, 20, -20, 20, 0, 80], 
                                 simp_field_resolution=1.0, 
                                 degree=3)
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(morphopt.simp.Solver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.Params):

            super().__init__(params=params,
                            num_process=1)

    class Updater(morphopt.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: morphopt.Params, *args, **kwargs):
            super().__init__(materials=self.UpdaterMaterials(params=params),
                            *args, **kwargs)

        class UpdaterMaterials(morphopt.simp.UpdaterMaterials):
            """
            Material updater based on SIMP control points.
            """

            def __init__(self, params: morphopt.Params):
                super().__init__(
                    params=params,
                    max_step_iter=50,
                    max_step_length=0.2,
                )

                shape_derivative = self.objectivefuncs.Sensitivity(normalize_gradient=False)
                self.add_objective_function(shape_derivative)

                density_regularization = self.objectivefuncs.DensityFieldMinimize(scale=1e-12)
                self.add_objective_function(density_regularization)

                # Keep SIMP control points within [0, 1] and avoid singular material values.
                self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=0.001, threshold=0.0, p=2))
                self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=0.999, threshold=0.0, p=2))

                self.if_update = True
    
if __name__ == '__main__':

    morphopt.start_optimization(device='cpu', restart_per_iteration=10)
