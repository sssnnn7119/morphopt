import os
os.environ["MPLBACKEND"] = "Agg"
import math
import morphopt
import torchfea
from typing import Any


class ThisController(morphopt.Controller):

    def __init__(self) -> None:
        super().__init__(
            path_result_folder='.results/', opt_label='BendingActuator'
        )

    class ObjectiveFunction(morphopt.ObjectiveFunction):

        def __init__(self) -> None:
            super().__init__()

        def objective_function(self) -> Any:
            return sum(self._objective_values())

        def _objective_values(self) -> list[Any]:
            def objective_term_0() -> Any:
                self.set_step('load_case_1')
                assembly = self.fe.assembly
                state = assembly._GC2RGC(
                    self.fe_results['load_case_1'].GC.to(assembly.device)
                )
                reference_point = assembly.get_reference_point('RP_1')
                return state[reference_point._RGC_index].reshape(-1)[4]
            return [(1.0) * (objective_term_0() - 2.0) ** 2]

        def get_metrics(self) -> Any:
            def metric_term_0() -> Any:
                self.set_step('load_case_1')
                assembly = self.fe.assembly
                state = assembly._GC2RGC(
                    self.fe_results['load_case_1'].GC.to(assembly.device)
                )
                reference_point = assembly.get_reference_point('RP_1')
                return state[reference_point._RGC_index].reshape(-1)[4]
            metrics = {}
            for name, value in [
                ('', metric_term_0()),
                ('', {f'objective_{index}': value for index, value in enumerate(self._objective_values())}),
            ]:
                if isinstance(value, dict):
                    entries = value
                elif isinstance(value, (list, tuple)):
                    entries = {
                        f'{name}_{index}' if name else str(len(metrics) + index): item
                        for index, item in enumerate(value)
                    }
                else:
                    entries = {name or str(len(metrics)): value}
                if metrics.keys() & entries.keys():
                    raise ValueError('Metric names must be unique.')
                metrics.update(entries)
            return metrics

    class Params(morphopt.Params):

        class GeometryParams(morphopt.GeometryParams):


            class BoundaryPart(morphopt.BoundaryPart):

                def define_surfaces(self) -> None:
                    surface_0 = self.BSP.initialize_cylinder(r0=8.0, length=80.0, seed_size=1.0, num_U_ratio=1, num_V_ratio=1, degree=3, init_location=[0.0, 0.0, 0.0], perturbation_L=10.0)
                    surface_0.is_updatable = True
                    self.add_surface_interface(surface_0)
                    surface_1 = self.BSP.initialize_cylinder(r0=4.0, length=74.0, seed_size=1.0, num_U_ratio=1, num_V_ratio=1, degree=3, init_location=[0.0, 0.0, 3.0], perturbation_L=10.0)
                    surface_1.is_updatable = True
                    self.add_surface_interface(surface_1)
                    surface_0.add_constraint(surface_0.mirror(plane='xz', offset=0.0))
                    surface_1.add_constraint(surface_1.mirror(plane='xz', offset=0.0))

                def define_instance(self) -> None:

                    self.add_instance('part1', 'part1-1', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

            def define_interface(self) -> None:

                # BoundaryPart
                part_0 = self.BoundaryPart(
                    fea_seed_size=1.0,
                    mesh_order=1,
                    exterior_surface='surface_0_All',
                )
                self.add_interface(part_0, name='part1')


        class FEAParams(morphopt.FEAParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:
                self.add_interface(self.Pressure(instance_name='part1-1', surface_name='surface_1_All'), name='pressure_1')
                self.add_interface(self.ReferencePoint(rp_location=[0.0, 0.0, 80.0]), name='RP_1')
                self.add_interface(self.Couple(rp_name='RP_1', instance_name='part1-1', set_nodes_name='surface_0_Head'), name='couple_1')
                self.add_interface(self.BoundaryCondition(instance_name='part1-1', set_nodes_name='surface_0_Bottom', index_dof=[0, 1, 2]), name='bc_1')

            def define_steps(self) -> None:
                self.add_step('load_case_1')
                self.set_step_params('load_case_1', 'pressure_1', [0.06])

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
            super().__init__(params=params, device=None)

        class UpdaterBoundaryPart(morphopt.UpdaterBoundaryPart):

            def __init__(self) -> None:
                super().__init__(
                    max_step_iter=50,
                    max_step_length=0.5,
                    step_length_strategy=self.strategies.FixedStepLength(),
                    constraint_weight_strategy=self.strategies.AdaptiveShapeWeights(
                        initial_tolerance=0.05,
                        final_tolerance=0.0,
                        tightening_increment=0.0002,
                        violation_tolerance=0.1,
                        weight_change_limit=10.0,
                    ),
                )

            def define_objective(self) -> None:
                self.add_objective_function(self.objectivefuncs.QuadraticShapeDerivative(memory_size=10))
                self.add_constraints(self.objectivefuncs.Fairness(max_curvature=1.0))
                self.add_constraints(self.objectivefuncs.Distance(min_distance=[[2.5, 2.5], [2.5, 2.5]]))
                self.add_constraints(self.objectivefuncs.boundarys.Cylinder(radius=10.0, height=80.0, bottom=0.0))


if __name__ == "__main__":
    morphopt.start_optimization(device='cpu', restart_per_iteration=20)
