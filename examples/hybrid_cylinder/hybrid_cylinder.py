import os
os.environ["MPLBACKEND"] = "Agg"
import morphopt
import torchfea
from typing import Any


import torch


design_length = 16.0

def tip_motion(objective, step):
    objective.set_step(step)
    assembly = objective.fe.assembly
    state = assembly._GC2RGC(objective.fe_results[step].GC.to(assembly.device))
    return state[assembly.get_reference_point("RP_tip")._RGC_index].reshape(-1)


class ThisController(morphopt.Controller):

    def __init__(self) -> None:
        super().__init__(
            path_result_folder='.results/', opt_label='HybridCylinder'
        )

    class ObjectiveFunction(morphopt.ObjectiveFunction):

        def __init__(self) -> None:
            super().__init__()

        def objective_function(self) -> Any:
            def objective_term_1() -> Any:
                self.set_step('load_case_1')
                assembly = self.fe.assembly
                state = assembly._GC2RGC(
                    self.fe_results['load_case_1'].GC.to(assembly.device)
                )
                reference_point = assembly.get_reference_point('RP_tip')
                return state[reference_point._RGC_index].reshape(-1)[0]
            def objective_term_2() -> Any:
                self.set_step('load_case_1')
                assembly = self.fe.assembly
                state = assembly._GC2RGC(
                    self.fe_results['load_case_1'].GC.to(assembly.device)
                )
                reference_point = assembly.get_reference_point('RP_tip')
                return state[reference_point._RGC_index].reshape(-1)[1]
            def objective_term_3() -> Any:
                self.set_step('load_case_1')
                assembly = self.fe.assembly
                state = assembly._GC2RGC(
                    self.fe_results['load_case_1'].GC.to(assembly.device)
                )
                reference_point = assembly.get_reference_point('RP_tip')
                return state[reference_point._RGC_index].reshape(-1)[2]
            return (44.44444444444444) * (objective_term_1() - 0.0) ** 2 + (44.44444444444444) * (objective_term_2() - 0.0) ** 2 + (44.44444444444444) * (objective_term_3() - 0.15) ** 2

        def get_metrics(self) -> Any:
            def metric_term_1() -> Any:
                return [tip_motion(self, "load_case_1")[2]]
            metrics = []
            metric_value_1 = metric_term_1()
            if isinstance(metric_value_1, (list, tuple)):
                metrics.extend(metric_value_1)
            else:
                metrics.append(metric_value_1)
            return metrics

    class Params(morphopt.Params):

        class GeometryParams(morphopt.GeometryParams):


            class BoundaryPart(morphopt.BoundaryPart):

                def define_surfaces(self) -> None:
                    surface_0 = self.BREPSurface(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets/outer-cylinder.stp'), control_point_spacing=1.0)
                    surface_0.is_updatable = False
                    self.add_surface_interface(surface_0)
                    surface_1 = self.BSP.initialize_cylinder(r0=1.4, length=14.0, seed_size=2.0, num_U_ratio=1, num_V_ratio=1, degree=2, init_location=[-0.0, 0.0, 1.0], maxR=0.2, maxC=1.0, maxFF=0.2, perturbation_L=-1.0, flip=True)
                    surface_1.is_updatable = True
                    self.add_surface_interface(surface_1)

                def define_instance(self) -> None:

                    self.add_instance('body', 'body-1', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

            def define_interface(self) -> None:

                # BoundaryPart
                part_0 = self.BoundaryPart(
                    fea_seed_size=2.0,
                    mesh_order=1,
                    exterior_surface='surface_0_All',
                )
                self.add_interface(part_0, name='body')


        class FEAParams(morphopt.FEAParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:
                self.add_interface(self.Pressure(instance_name='body-1', surface_name='surface_1_All'), name='pressure_1')
                self.add_interface(self.BoundaryCondition(instance_name='body-1', set_nodes_name='face_2_nodes', index_dof=[0, 1, 2]), name='base_fixed')
                self.add_interface(self.ReferencePoint(rp_location=[0.0, 0.0, 16.0]), name='RP_tip')
                self.add_interface(self.Couple(rp_name='RP_tip', instance_name='body-1', set_nodes_name='face_1_nodes'), name='tip_coupling')

            def define_steps(self) -> None:
                self.add_step('load_case_1')
                self.set_step_params('load_case_1', 'pressure_1', [0.02])

        class MaterialsParams(morphopt.MaterialsParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:

                self.add_interface(morphopt.HomogeneousMaterial(
                    material_parameters=self.models.NeoHookeanLnJParams(mu=0.3, kappa=3.0),
                    part_name='body',
                    elementname='',
                    density=1.08e-09,
                ), name='body_material')

        def __init__(self) -> None:
            super().__init__(
                geometry=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialsParams()
            )

    class Solver(morphopt.Solver):

        def __init__(self, params: Any) -> None:

            super().__init__(params=params, num_process=1, process_devices=['cpu'], task_step_list=[['load_case_1']])

    class Updater(morphopt.Updaters):

        def define_updater(self) -> None:
            self.add_geometry_updater(self.UpdaterBoundaryPart(), name='body')

        def __init__(self, params: Any) -> None:
            super().__init__(params=params, device='cpu')

        class UpdaterBoundaryPart(morphopt.UpdaterBoundaryPart):

            def __init__(self) -> None:
                super().__init__(max_step_iter=5, max_step_length=0.5)

            def define_objective(self) -> None:
                self.add_objective_function(self.objectivefuncs.ShapeDerivative())
                self.add_constraints(self.objectivefuncs.Fairness())
                self.add_constraints(self.objectivefuncs.Distance(min_distance=[[1.0, 1.0], [1.0, 1.0]]))
                self.add_constraints(self.objectivefuncs.boundarys.Cylinder(radius=4.0, height=16.0, bottom=0.0))


if __name__ == "__main__":
    morphopt.start_optimization(device='cpu', restart_per_iteration=10)
