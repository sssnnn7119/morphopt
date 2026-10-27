import os
os.environ["MPLBACKEND"] = "Agg"
import morphopt
import torchfea
from typing import Any


class ThisController(morphopt.Controller):

    def __init__(self) -> None:
        super().__init__(
            path_result_folder='.results/', opt_label='WorkspaceObjective'
        )

    class ObjectiveFunction(morphopt.ObjectiveFunction):

        def __init__(self) -> None:
            super().__init__()
            self.jacobian_needed = ['pressure_1', 'pressure_2']

        def objective_function(self) -> Any:
            def objective_term_1() -> Any:
                assembly = self.fe.assembly
                reference_point = assembly.get_reference_point('RP_1')
                start = assembly._GC_list_indexStart[reference_point._RGC_index]
                axes = [0, 2]
                # Load case, Gauss weight, orientation, tangent input indices.
                samples = [
                    ('workspace_1_case_1', 0.03, -1.0, 1),
                    ('workspace_1_case_2', 0.03, -1.0, 1),
                    ('workspace_1_case_3', 0.03, 1.0, 1),
                    ('workspace_1_case_4', 0.03, 1.0, 1),
                    ('workspace_1_case_5', 0.03, 1.0, 0),
                    ('workspace_1_case_6', 0.03, 1.0, 0),
                    ('workspace_1_case_7', 0.03, -1.0, 0),
                    ('workspace_1_case_8', 0.03, -1.0, 0),
                ]
                integral = 0.0
                for case_name, weight, orientation, tangent_axis in samples:
                    self.set_step(case_name)
                    result = self.fe_results[case_name]
                    state = assembly._GC2RGC(result.GC.to(assembly.device))
                    motion = state[reference_point._RGC_index].reshape(-1)[axes]
                    jacobian_0 = (
                        result.jacobian['pressure_1'][start:start + 6, 0].to(motion.device)
                    )[axes]
                    jacobian_1 = (
                        result.jacobian['pressure_2'][start:start + 6, 0].to(motion.device)
                    )[axes]
                    jacobians = [jacobian_0, jacobian_1]
                    tangent = jacobians[tangent_axis]
                    # Counter-clockwise boundary: x dy - y dx.
                    integrand = motion[0] * tangent[1] - motion[1] * tangent[0]
                    integral = integral + weight * orientation * integrand
                return abs(integral) / 2.0
            return -(1.0) * objective_term_1() / 1.0

        def get_metrics(self) -> Any:
            metrics = []
            return metrics

    class Params(morphopt.Params):

        class GeometryParams(morphopt.GeometryParams):


            class BoundaryPart(morphopt.BoundaryPart):

                def define_surfaces(self) -> None:
                    surface_0 = self.BSP.initialize_cylinder(r0=8.0, length=100.0, seed_size=1.0, num_U_ratio=1, num_V_ratio=1, degree=3, init_location=[0.0, 0.0, 0.0], maxR=0.2, maxC=2.0, maxFF=0.2, perturbation_L=10.0, flip=False)
                    surface_0.is_updatable = True
                    self.add_surface_interface(surface_0)
                    surface_1 = self.BSP.initialize_cylinder(r0=4.0, length=44.0, seed_size=1.0, num_U_ratio=1, num_V_ratio=1, degree=3, init_location=[0.0, 0.0, 3.0], maxR=0.2, maxC=2.0, maxFF=0.2, perturbation_L=10.0, flip=True)
                    surface_1.is_updatable = True
                    self.add_surface_interface(surface_1)
                    surface_2 = self.BSP.initialize_cylinder(r0=4.0, length=44.0, seed_size=1.0, num_U_ratio=1, num_V_ratio=1, degree=3, init_location=[0.0, 0.0, 53.0], maxR=0.2, maxC=2.0, maxFF=0.2, perturbation_L=10.0, flip=True)
                    surface_2.is_updatable = True
                    self.add_surface_interface(surface_2)
                    surface_0.add_constraint(surface_0.mirror(plane='xz', offset=0.0))
                    surface_1.add_constraint(surface_1.mirror(plane='xz', offset=0.0))
                    surface_2.add_constraint(surface_2.mirror(plane='xz', offset=0.0))

                def define_instance(self) -> None:

                    self.add_instance('part1', 'part1-1', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

            def define_interface(self) -> None:

                # BoundaryPart
                part_0 = self.BoundaryPart(
                    fea_seed_size=2.0,
                    mesh_order=2,
                    exterior_surface='surface_0_All',
                )
                self.add_interface(part_0, name='part1')


        class FEAParams(morphopt.FEAParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:
                self.add_interface(self.Pressure(instance_name='part1-1', surface_name='surface_1_All'), name='pressure_1')
                self.add_interface(self.ReferencePoint(rp_location=[0.0, 0.0, 100.0]), name='RP_1')
                self.add_interface(self.Couple(rp_name='RP_1', instance_name='part1-1', set_nodes_name='surface_0_Head'), name='couple_1')
                self.add_interface(self.BoundaryCondition(instance_name='part1-1', set_nodes_name='surface_0_Bottom', index_dof=[0, 1, 2]), name='bc_1')
                self.add_interface(self.Pressure(instance_name='part1-1', surface_name='surface_2_All'), name='pressure_2')

            def define_steps(self) -> None:
                self.add_step('workspace_1_case_1')
                self.set_step_params('workspace_1_case_1', 'pressure_1', [0.0])
                self.set_step_params('workspace_1_case_1', 'pressure_2', [0.01267949192431123])
                self.add_step('workspace_1_case_2')
                self.set_step_params('workspace_1_case_2', 'pressure_1', [0.0])
                self.set_step_params('workspace_1_case_2', 'pressure_2', [0.04732050807568877])
                self.add_step('workspace_1_case_3')
                self.set_step_params('workspace_1_case_3', 'pressure_1', [0.06])
                self.set_step_params('workspace_1_case_3', 'pressure_2', [0.01267949192431123])
                self.add_step('workspace_1_case_4')
                self.set_step_params('workspace_1_case_4', 'pressure_1', [0.06])
                self.set_step_params('workspace_1_case_4', 'pressure_2', [0.04732050807568877])
                self.add_step('workspace_1_case_5')
                self.set_step_params('workspace_1_case_5', 'pressure_1', [0.01267949192431123])
                self.set_step_params('workspace_1_case_5', 'pressure_2', [0.0])
                self.add_step('workspace_1_case_6')
                self.set_step_params('workspace_1_case_6', 'pressure_1', [0.04732050807568877])
                self.set_step_params('workspace_1_case_6', 'pressure_2', [0.0])
                self.add_step('workspace_1_case_7')
                self.set_step_params('workspace_1_case_7', 'pressure_1', [0.01267949192431123])
                self.set_step_params('workspace_1_case_7', 'pressure_2', [0.06])
                self.add_step('workspace_1_case_8')
                self.set_step_params('workspace_1_case_8', 'pressure_1', [0.04732050807568877])
                self.set_step_params('workspace_1_case_8', 'pressure_2', [0.06])

        class MaterialsParams(morphopt.MaterialsParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:

                self.add_interface(morphopt.HomogeneousMaterial(
                    material_parameters=self.models.NeoHookeanLnJParams(mu=0.482, kappa=4.8),
                    part_name='part1',
                    elementname='',
                    density=1.08e-09,
                ), name='material_1')

        def __init__(self) -> None:
            super().__init__(
                geometry=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialsParams()
            )

    class Solver(morphopt.Solver):

        def __init__(self, params: Any) -> None:

            super().__init__(params=params, num_process=1, process_devices=['cpu'])

    class Updater(morphopt.Updaters):

        def define_updater(self) -> None:
            self.add_geometry_updater(self.UpdaterBoundaryPart(), name='part1')

        def __init__(self, params: Any) -> None:
            super().__init__(params=params, device='cpu')

        class UpdaterBoundaryPart(morphopt.UpdaterBoundaryPart):

            def __init__(self) -> None:
                super().__init__(max_step_iter=300, max_step_length=0.5)

            def define_objective(self) -> None:
                self.add_objective_function(self.objectivefuncs.ShapeDerivative())
                self.add_constraints(self.objectivefuncs.Fairness())
                self.add_constraints(self.objectivefuncs.Distance(min_distance=[[2.5, 2.5, 2.5], [2.5, 2.5, 2.5], [2.5, 2.5, 2.5]]))
                self.add_constraints(self.objectivefuncs.boundarys.Cylinder(radius=15.0, height=100.0, bottom=0.0))


if __name__ == "__main__":
    morphopt.start_optimization(device='cpu', restart_per_iteration=10)
