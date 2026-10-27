import os
os.environ["MPLBACKEND"] = "Agg"
import morphopt
import torchfea
from typing import Any


import numpy as np
import torch
import torchfea

mumax = 10.0
minratio = 1e-7
cylinder_x = [80.0, 70.0, 60.0, 50.0]

def _surface_at_coordinate(part, element_name, axis, coordinate, tolerance=1e-8):
    element = part.elems[element_name]
    selected = []
    for element_ids, side in element.extract_boundary_surface_set():
        ids = np.asarray(element_ids, dtype=np.int64)
        index = torch.as_tensor(ids, dtype=torch.long, device=element._elems.device)
        face_nodes = element._elems[index][:, element.surfaceid_map[int(side)]]
        on_plane = (part.nodes[face_nodes][..., axis] - float(coordinate)).abs().amax(dim=1)
        matching = ids[(on_plane <= tolerance).detach().cpu().numpy()]
        if len(matching):
            selected.append((matching, int(side)))
    if not selected:
        raise RuntimeError(f"No boundary faces found on axis {axis}={coordinate}.")
    return selected

def _get_volume_fraction(objective):
    elems = objective.fe.assembly._parts["final_model"].elems["C3D4"]
    ratio = elems.materials["material-0"].scale
    weights = elems.gaussian_weight
    return (weights * ratio).sum() / weights.sum()

def _add_gripper_sets(part):
    element_name = "C3D4"
    xmin_nodes = torch.where((part.nodes[:, 0] - 0.0).abs() <= 1e-8)[0]
    if not xmin_nodes.numel():
        raise RuntimeError("No gripper nodes found on x=0.")
    part.add_node_set("nodes_xmin", xmin_nodes)
    part.add_surface_set("surface_zmax", _surface_at_coordinate(part, element_name, 2, 0.0))
    part.add_surface_set("surface_0_All", list(part.surfaces["extern"]))
    part.exterior_surface = "surface_0_All"

def _build_gripper_part(part_name):
    cad = torchfea.cad.CADModel()
    history = cad.add_part(part_name)
    history.add_box(x=0.0, y=-0.5, z=-30.0, dx=80.0, dy=1.0, dz=30.0)
    part = cad.mesh_part(part_name, mesh_size=0.5)
    _add_gripper_sets(part)
    return part

def _build_cylinder_part(part_name):
    cad = torchfea.cad.CADModel()
    history = cad.add_part(part_name)
    history.add_cylinder(x=80.0, y=-10.0, z=15.0, dy=20.0, radius=15.0)
    part = cad.mesh_part(part_name, mesh_size=1.5)
    part.add_node_set("cylinder", part.set_nodes["all"])
    return part


class GripperPartBuilder(morphopt.BasePart):
    def build_part(self, path_result=None, pools=None):
        return _build_gripper_part(self.part_name)


class CylinderPartBuilder(morphopt.BasePart):
    def build_part(self, path_result=None, pools=None):
        return _build_cylinder_part(self.part_name)


class GripperObjective(morphopt.ObjectiveFunction):
    def objective_function(self):
        loss_list = []
        for stepidx in range(self.num_tasks):
            step = f"load_case_{stepidx + 1}"
            self.set_step(step)
            total_force = self.fe.assembly._assemble_generalized_Matrix(GC=self.fe_results[step].GC)[0]
            instance = self.fe.assembly.get_instance("final_model")
            starts = self.fe.assembly._RGC_list_indexStart
            force = total_force[starts[instance._RGC_index]:starts[instance._RGC_index + 1]].reshape([-1, 3])
            loss_list.append(torch.exp(force[:, 0].sum()) - force[:, 2].sum())
        return torch.stack(loss_list).sum()

    def get_metrics(self):
        metrics = []
        for stepidx in range(self.num_tasks):
            step = f"load_case_{stepidx + 1}"
            self.set_step(step)
            total_force = self.fe.assembly._assemble_generalized_Matrix(GC=self.fe_results[step].GC)[0]
            instance = self.fe.assembly.get_instance("final_model")
            starts = self.fe.assembly._RGC_list_indexStart
            force = total_force[starts[instance._RGC_index]:starts[instance._RGC_index + 1]].reshape([-1, 3])
            metrics.extend([force[:, 0].sum(), force[:, 2].sum()])
        return metrics + [_get_volume_fraction(self)]


class GripperMaterial(morphopt.SIMP_BSPFieldMaterials):
    def reinitialize(self, iteration, *args, **kwargs):
        control_points = self._cps.reshape(self._bsp_size[0], self._bsp_size[1], self._bsp_size[2]).clone()
        control_points[:, :, -2:] = 15.0
        self._cps = control_points.reshape_as(self._cps)
        return super().reinitialize(iteration, *args, **kwargs)



class ThisController(morphopt.Controller):

    def __init__(self) -> None:
        super().__init__(
            path_result_folder='.results/', opt_label='SIMPGripper'
        )

    class ObjectiveFunction(GripperObjective):

        def __init__(self) -> None:
            super().__init__()



    class Params(morphopt.Params):

        class GeometryParams(morphopt.GeometryParams):


            class BasePart(GripperPartBuilder):


                def define_instance(self) -> None:

                    self.add_instance('final_model', 'final_model', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

            class BasePart2(CylinderPartBuilder):


                def define_instance(self) -> None:

                    self.add_instance('cylinder', 'cylinder80', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

                    self.add_instance('cylinder', 'cylinder70', [-10.0, 0.0, 0.0, 0.0, 0.0, 0.0])

                    self.add_instance('cylinder', 'cylinder60', [-20.0, 0.0, 0.0, 0.0, 0.0, 0.0])

                    self.add_instance('cylinder', 'cylinder50', [-30.0, 0.0, 0.0, 0.0, 0.0, 0.0])

            def define_interface(self) -> None:

                # BasePart
                part_0 = self.BasePart(
                    exterior_surface='surface_0_All',
                )
                self.add_interface(part_0, name='final_model')

                # BasePart
                part_1 = self.BasePart2(
                    exterior_surface='extern',
                )
                self.add_interface(part_1, name='cylinder')


        class FEAParams(morphopt.FEAParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:
                self.add_interface(self.ReferencePoint(rp_location=[0, 0, 0]), name='RPBase')
                self.add_interface(self.Couple(rp_name='RPBase', instance_name='final_model', set_nodes_name='nodes_xmin'), name='couple_base')
                self.add_interface(self.ReferencePointBoundaryCondition(rp_name='RPBase', index_dof=[0, 1, 2, 3, 4, 5]), name='BC_RPBase')
                self.add_interface(self.BoundaryCondition(instance_name='final_model', set_nodes_name='all', index_dof=[1]), name='BC_Symmetry')
                self.add_interface(self.ReferencePoint(rp_location=[80.0, 0, 15]), name='RPCylinder80')
                self.add_interface(self.Couple(rp_name='RPCylinder80', instance_name='cylinder80', set_nodes_name='cylinder'), name='couple_cylinder80')
                self.add_interface(self.ReferencePointBoundaryCondition(rp_name='RPCylinder80', index_dof=[0, 1, 3, 4, 5]), name='BC_RPCylinder80')
                self.add_interface(self.PenaltyDoF(obj_name='RPCylinder80', s=2, obj_type='auto'), name='Penalty_RPCylinder80_Z')
                self.add_interface(self.Contact(instance_name1='final_model', surface_name1='surface_zmax', instance_name2='cylinder80', surface_name2='extern', penalty_threshold_h=1.0), name='Contact_cylinder80')
                self.add_interface(self.ReferencePoint(rp_location=[70.0, 0, 15]), name='RPCylinder70')
                self.add_interface(self.Couple(rp_name='RPCylinder70', instance_name='cylinder70', set_nodes_name='cylinder'), name='couple_cylinder70')
                self.add_interface(self.ReferencePointBoundaryCondition(rp_name='RPCylinder70', index_dof=[0, 1, 3, 4, 5]), name='BC_RPCylinder70')
                self.add_interface(self.PenaltyDoF(obj_name='RPCylinder70', s=2, obj_type='auto'), name='Penalty_RPCylinder70_Z')
                self.add_interface(self.Contact(instance_name1='final_model', surface_name1='surface_zmax', instance_name2='cylinder70', surface_name2='extern', penalty_threshold_h=1.0), name='Contact_cylinder70')
                self.add_interface(self.ReferencePoint(rp_location=[60.0, 0, 15]), name='RPCylinder60')
                self.add_interface(self.Couple(rp_name='RPCylinder60', instance_name='cylinder60', set_nodes_name='cylinder'), name='couple_cylinder60')
                self.add_interface(self.ReferencePointBoundaryCondition(rp_name='RPCylinder60', index_dof=[0, 1, 3, 4, 5]), name='BC_RPCylinder60')
                self.add_interface(self.PenaltyDoF(obj_name='RPCylinder60', s=2, obj_type='auto'), name='Penalty_RPCylinder60_Z')
                self.add_interface(self.Contact(instance_name1='final_model', surface_name1='surface_zmax', instance_name2='cylinder60', surface_name2='extern', penalty_threshold_h=1.0), name='Contact_cylinder60')
                self.add_interface(self.ReferencePoint(rp_location=[50.0, 0, 15]), name='RPCylinder50')
                self.add_interface(self.Couple(rp_name='RPCylinder50', instance_name='cylinder50', set_nodes_name='cylinder'), name='couple_cylinder50')
                self.add_interface(self.ReferencePointBoundaryCondition(rp_name='RPCylinder50', index_dof=[0, 1, 3, 4, 5]), name='BC_RPCylinder50')
                self.add_interface(self.PenaltyDoF(obj_name='RPCylinder50', s=2, obj_type='auto'), name='Penalty_RPCylinder50_Z')
                self.add_interface(self.Contact(instance_name1='final_model', surface_name1='surface_zmax', instance_name2='cylinder50', surface_name2='extern', penalty_threshold_h=1.0), name='Contact_cylinder50')

            def define_steps(self) -> None:
                self.add_step('load_case_1')
                self.set_step_params('load_case_1', 'Penalty_RPCylinder80_Z', [100.0, -10.0])
                self.set_step_params('load_case_1', 'Penalty_RPCylinder70_Z', [100.0, 0.0])
                self.set_step_params('load_case_1', 'Penalty_RPCylinder60_Z', [100.0, 0.0])
                self.set_step_params('load_case_1', 'Penalty_RPCylinder50_Z', [100.0, 0.0])
                self.add_step('load_case_2')
                self.set_step_params('load_case_2', 'Penalty_RPCylinder80_Z', [100.0, 0.0])
                self.set_step_params('load_case_2', 'Penalty_RPCylinder70_Z', [100.0, -10.0])
                self.set_step_params('load_case_2', 'Penalty_RPCylinder60_Z', [100.0, 0.0])
                self.set_step_params('load_case_2', 'Penalty_RPCylinder50_Z', [100.0, 0.0])
                self.add_step('load_case_3')
                self.set_step_params('load_case_3', 'Penalty_RPCylinder80_Z', [100.0, 0.0])
                self.set_step_params('load_case_3', 'Penalty_RPCylinder70_Z', [100.0, 0.0])
                self.set_step_params('load_case_3', 'Penalty_RPCylinder60_Z', [100.0, -10.0])
                self.set_step_params('load_case_3', 'Penalty_RPCylinder50_Z', [100.0, 0.0])
                self.add_step('load_case_4')
                self.set_step_params('load_case_4', 'Penalty_RPCylinder80_Z', [100.0, 0.0])
                self.set_step_params('load_case_4', 'Penalty_RPCylinder70_Z', [100.0, 0.0])
                self.set_step_params('load_case_4', 'Penalty_RPCylinder60_Z', [100.0, 0.0])
                self.set_step_params('load_case_4', 'Penalty_RPCylinder50_Z', [100.0, -10.0])

        class MaterialsParams(morphopt.MaterialsParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:

                self.add_interface(GripperMaterial(
                    material_parameters=self.models.NeoHookeanLnJParams(mu=10.0, kappa=100.0),
                    part_name='final_model',
                    elementname='C3D4',
                    mumax=10.0,
                    kappamax=100.0,
                    density=1.08e-09,
                    simp_ratio_min=1e-07,
                    initial_ratio=-2.0,
                    voidpenalfactor=0.0,
                    materialpenalty=8,
                    bounding_box=[0.0, 80.0, -1.0, 1.0, -30.0, 0.0],
                    simp_field_resolution=1.0,
                    degree=2,
                ), name='body')

        def __init__(self) -> None:
            super().__init__(
                geometry=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialsParams()
            )

    class Solver(morphopt.Solver):

        def __init__(self, params: Any) -> None:

            super().__init__(params=params, num_process=1, process_devices=['cpu'])

    class Updater(morphopt.Updaters):

        def define_updater(self) -> None:
            self.add_material_updater(self.UpdaterSIMPMaterial(), name='body')

        def __init__(self, params: Any) -> None:
            super().__init__(params=params, device='cpu')

        class UpdaterSIMPMaterial(morphopt.UpdaterSIMPMaterial):

            def __init__(self) -> None:
                super().__init__(max_step_iter=100, max_step_length=1.0)

            def define_objective(self) -> None:
                self.add_objective_function(self.objectivefuncs.Sensitivity(normalize_gradient=False))
                self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=-15.0, threshold=0.0, p=2))
                self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=15.0, threshold=0.0, p=2))
                self.add_constraints(self.objectivefuncs.VolFrac(volfrac_min=0.3, volfrac_max=0.4, penalty=1000000.0, elementname='C3D4'))
                self.if_update = True


if __name__ == "__main__":
    morphopt.start_optimization(device='cpu', restart_per_iteration=20)
