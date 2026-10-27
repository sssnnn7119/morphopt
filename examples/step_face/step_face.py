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
            path_result_folder='.results/', opt_label='StepFace'
        )

    class ObjectiveFunction(morphopt.ObjectiveFunction):

        def __init__(self) -> None:
            super().__init__()

        def objective_function(self) -> Any:
            def objective_term_1() -> Any:
                self.set_step('compression')
                assembly = self.fe.assembly
                state = assembly._GC2RGC(
                    self.fe_results['compression'].GC.to(assembly.device)
                )
                reference_point = assembly.get_reference_point('tip')
                return state[reference_point._RGC_index].reshape(-1)[2]
            return (1.0) * objective_term_1()

        def get_metrics(self) -> Any:
            def metric_term_1() -> Any:
                return [self.fe_results["compression"].GC[-4].detach().cpu().item()]
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
                    surface_0 = self.BREPSurface(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets/cylinder.stp'), control_point_spacing=0.8)
                    surface_0.select_design_faces(['face_0'])
                    surface_0.is_updatable = True
                    self.add_surface_interface(surface_0)

                def define_instance(self) -> None:

                    self.add_instance('body', 'body-1', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

            def define_interface(self) -> None:

                # BoundaryPart
                part_0 = self.BoundaryPart(
                    fea_seed_size=1.2,
                    mesh_order=1,
                    exterior_surface='surface_0_All',
                )
                self.add_interface(part_0, name='body')


        class FEAParams(morphopt.FEAParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:
                self.add_interface(self.Pressure(instance_name='body-1', surface_name='surface_0_top'), name='pressure')
                self.add_interface(self.BoundaryCondition(instance_name='body-1', set_nodes_name='surface_0_bottom_nodes', index_dof=[0, 1, 2]), name='fixed')
                self.add_interface(self.ReferencePoint(rp_location=[0.0, 0.0, 5.0]), name='tip')
                self.add_interface(self.Couple(rp_name='tip', instance_name='body-1', set_nodes_name='surface_0_top_nodes'), name='coupling')

            def define_steps(self) -> None:
                self.add_step('compression')
                self.set_step_params('compression', 'pressure', [0.05])

        class MaterialsParams(morphopt.MaterialsParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:

                self.add_interface(morphopt.HomogeneousMaterial(
                    material_parameters=self.models.NeoHookeanLnJParams(mu=10.0, kappa=100.0),
                    part_name='body',
                    elementname='',
                    density=1e-09,
                ), name='material')

        def __init__(self) -> None:
            super().__init__(
                geometry=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialsParams()
            )

    class Solver(morphopt.Solver):

        def __init__(self, params: Any) -> None:

            super().__init__(params=params, num_process=1, process_devices=['cpu'], task_step_list=[['compression']])

    class Updater(morphopt.Updaters):

        def define_updater(self) -> None:
            self.add_geometry_updater(self.UpdaterBoundaryPart(), name='body')

        def __init__(self, params: Any) -> None:
            super().__init__(params=params, device='cpu')

        class UpdaterBoundaryPart(morphopt.UpdaterBoundaryPart):

            def __init__(self) -> None:
                super().__init__(max_step_iter=3, max_step_length=0.02)

            def define_objective(self) -> None:
                self.add_objective_function(self.objectivefuncs.ShapeDerivative())


if __name__ == "__main__":
    morphopt.start_optimization(device='cpu', restart_per_iteration=10)
