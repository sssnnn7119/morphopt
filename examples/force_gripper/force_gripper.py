import os
os.environ["MPLBACKEND"] = "Agg"
import morphopt
import torchfea
from typing import Any


import numpy as np
import torch
import torchfea


mu_material = 0.482

kappa_material = 4.8

minratio = 1e-5

mesh_size = 1.0

field_resolution = 1.0

simp_degree = 2

finger_depth = 36.0

finger_height = 72.0

finger_width = (
    1.0  # Keep the single-layer physical thickness fixed as the mesh is refined.
)

simp_field_thickness = max(finger_width, simp_degree * field_resolution)

root_depth = 2 * finger_width

skin_depth = finger_width

initial_gap = 40.0

object_diameter = 32.0

closure_steps = np.arange(4.0, 15.0 + 0.5, 1.0).tolist()

working_stroke_start = 10.0

target_force = 5.0

initial_density = 0.35

void_penalty_factor = 1e-4

volume_fraction_max = (
    0.7  # Existing fixed-volume setting (min=max); design region only.
)

drive_stiffness = 1e3

contact_distance = 3.0

def _build_finger_part():
    """Conforming C3D20 bricks with shared solid/design interface nodes."""

    def coordinates(start, end):
        return np.linspace(
            start, end, max(1, int(np.ceil((end - start) / mesh_size))) + 1
        )

    x = np.concatenate(
        [
            coordinates(0.0, root_depth)[:-1],
            coordinates(root_depth, finger_depth - skin_depth)[:-1],
            coordinates(finger_depth - skin_depth, finger_depth),
        ]
    )
    # Build one linear brick layer, then add shared midside nodes below.
    y = np.array([-finger_width / 2, finger_width / 2])
    z = coordinates(0.0, finger_height / 2)
    nodes = np.stack(np.meshgrid(x, y, z, indexing="ij"), axis=-1).reshape(-1, 3)
    node_ids = np.arange(len(nodes)).reshape(len(x), len(y), len(z))
    offsets = [
        (0, 0, 0),
        (1, 0, 0),
        (1, 1, 0),
        (0, 1, 0),
        (0, 0, 1),
        (1, 0, 1),
        (1, 1, 1),
        (0, 1, 1),
    ]
    cells = np.array(
        [
            [node_ids[i + di, j + dj, k + dk] for di, dj, dk in offsets]
            for i in range(len(x) - 1)
            for j in range(len(y) - 1)
            for k in range(len(z) - 1)
        ]
    )
    tags = np.arange(len(cells))
    centres = nodes[cells].mean(axis=1)
    design = (centres[:, 0] > root_depth) & (centres[:, 0] < finger_depth - skin_depth)
    part = torchfea.Part(torch.as_tensor(nodes, dtype=torch.get_default_dtype()))
    # Construct the exterior before splitting, so internal interfaces are not
    # accidentally exposed as contact surfaces. Element tags remain unique.
    whole = torchfea.elements.C3D8(
        elems_index=torch.as_tensor(tags), elems=torch.as_tensor(cells)
    )
    exterior = whole.extract_boundary_surface_set()
    contact = []
    for ids, side in exterior:
        face_nodes = cells[ids][:, whole.surfaceid_map[side]]
        selected = np.all(np.isclose(nodes[face_nodes, 0], finger_depth), axis=1)
        if selected.any():
            contact.append((ids[selected], side))
    for name, mask in [("design", design), ("solid", ~design)]:
        part.add_element(
            torchfea.elements.C3D8(
                elems_index=torch.as_tensor(tags[mask]),
                elems=torch.as_tensor(cells[mask]),
            ),
            name=name,
        )
    part.add_node_set("all", np.arange(len(nodes)))
    part.add_node_set("root", np.flatnonzero(np.isclose(nodes[:, 0], 0.0)))
    part.add_node_set("symmetry", np.flatnonzero(np.isclose(nodes[:, 2], 0.0)))
    part.add_surface_set("extern", exterior)
    part.add_surface_set("contact", contact)
    # Convert both regions together so interface midside nodes are shared.
    # Node sets also gain midside nodes for all boundary conditions.
    part.convert_linear_to_quadratic_elements(["design", "solid"], ["design", "solid"])
    return part


def _force_displacement(objective, step_index):
    step = f"load_case_{step_index + 1}"
    objective.set_step(step)
    assembly = objective.fe.assembly
    rgc = assembly._GC2RGC(objective.fe_results[step].GC)
    reference_point = assembly.get_reference_point("RPCylinder")
    displacement = rgc[reference_point._RGC_index].reshape(-1)[0]
    drive = assembly.get_load("Drive")
    force = 2 * drive.k * (displacement - drive.target)
    return force, -displacement

def _volume_fraction(objective):
    elements = objective.fe.assembly._parts["finger"].elems["design"]
    ratio = elements.materials["material-0"].scale
    weights = elements.gaussian_weight
    return (weights * ratio).sum() / weights.sum()


class FingerPartBuilder(morphopt.BasePart):
    def define_instance(self):
        self.add_instance(self.part_name, "finger", [0, 0, 0, 0, 0, 0])

    def build_part(self, path_result=None, pools=None):
        return _build_finger_part()


class CylinderPartBuilder(morphopt.BasePart):
    def build_part(self, path_result=None, pools=None):
        cad = torchfea.cad.CADModel()
        history = cad.add_part(self.part_name)
        half_thickness = finger_width / 2
        history.add_cylinder(
            x=finger_depth + initial_gap / 2,
            y=-half_thickness,
            z=0.0,
            dx=0.0,
            dy=2 * half_thickness,
            dz=0.0,
            radius=object_diameter / 2,
        )
        return cad.mesh_part(self.part_name, mesh_size=mesh_size)


class ForceObjective(morphopt.ObjectiveFunction):
    def objective_function(self):
        start = closure_steps.index(working_stroke_start)
        forces = torch.stack([_force_displacement(self, index)[0] for index in range(start, len(closure_steps))])
        closures = forces.new_tensor(closure_steps[start:])
        error = ((forces - target_force) / target_force).square()
        return torch.trapezoid(error, closures) / (closures[-1] - closures[0])

    def get_metrics(self):
        forces = []
        errors = []
        for index, commanded_closure in enumerate(closure_steps):
            force, closure = _force_displacement(self, index)
            forces.append(force)
            errors.append(commanded_closure - closure)
        return forces + errors + [_volume_fraction(self)]


class ForceMaterial(morphopt.SIMP_BSPFieldMaterials):
    def update_variables(self, x_change, max_step_length=None):
        nx, ny, nz = self._bsp_size
        change = x_change.reshape(nx, ny, nz)
        change = change.mean(dim=1, keepdim=True).expand(nx, ny, nz)
        if isinstance(max_step_length, list):
            max_step_length = max_step_length[0]
        if max_step_length is not None and max_step_length.numel() > 1:
            max_step_length = max_step_length.reshape(nx, ny, nz)
            max_step_length = max_step_length.mean(dim=1, keepdim=True).expand(nx, ny, nz)
        if max_step_length is None:
            max_step_length = torch.ones_like(self._cps)
        if max_step_length.numel() > 1:
            max_step_length = max_step_length.reshape_as(self._cps)
        max_step_length = max_step_length.to(self._cps.device)
        self._cps = self._cps.detach() + (2.0 / torch.pi) * torch.atan(change.reshape_as(self._cps)) * max_step_length

    def reinitialize(self, iteration, *args, **kwargs):
        nx, ny, nz = self._bsp_size
        control_points = self._cps.reshape(nx, ny, nz)
        control_points = control_points.mean(dim=1, keepdim=True).expand(nx, ny, nz).clone()
        self._cps = control_points.reshape_as(self._cps)
        return super().reinitialize(iteration, *args, **kwargs)



class ThisController(morphopt.Controller):

    def __init__(self) -> None:
        super().__init__(
            path_result_folder='.results/', opt_label='ForceGripper'
        )

    class ObjectiveFunction(ForceObjective):

        def __init__(self) -> None:
            super().__init__()



    class Params(morphopt.Params):

        class GeometryParams(morphopt.GeometryParams):


            class BasePart(FingerPartBuilder):


                pass

            class BasePart2(CylinderPartBuilder):


                def define_instance(self) -> None:

                    self.add_instance('cylinder', 'cylinder', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

            def define_interface(self) -> None:

                # BasePart
                part_0 = self.BasePart(
                    exterior_surface='extern',
                )
                self.add_interface(part_0, name='finger')

                # BasePart
                part_1 = self.BasePart2(
                    exterior_surface='extern',
                )
                self.add_interface(part_1, name='cylinder')


        class FEAParams(morphopt.FEAParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:
                self.add_interface(self.BoundaryCondition(instance_name='finger', set_nodes_name='root', index_dof=[0, 2]), name='Root')
                self.add_interface(self.BoundaryCondition(instance_name='finger', set_nodes_name='all', index_dof=[1]), name='BC_PlaneStrain')
                self.add_interface(self.BoundaryCondition(instance_name='finger', set_nodes_name='symmetry', index_dof=[2]), name='BC_SymmetryZ')
                self.add_interface(self.ReferencePoint(rp_location=[56.0, 0.0, 0.0]), name='RPCylinder')
                self.add_interface(self.Couple(rp_name='RPCylinder', instance_name='cylinder', set_nodes_name='all'), name='RigidCylinder')
                self.add_interface(self.ReferencePointBoundaryCondition(rp_name='RPCylinder', index_dof=[1, 2, 3, 4, 5]), name='CylinderGuide')
                self.add_interface(self.PenaltyDoF(obj_name='RPCylinder', s=0, obj_type='auto'), name='Drive')
                self.add_interface(self.Contact(instance_name1='finger', surface_name1='contact', instance_name2='cylinder', surface_name2='extern', penalty_threshold_h=3.0), name='Contact')

            def define_steps(self) -> None:
                self.add_step('load_case_1')
                self.set_step_params('load_case_1', 'Drive', [500.0, -4.0])
                self.add_step('load_case_2')
                self.set_step_params('load_case_2', 'Drive', [500.0, -5.0])
                self.add_step('load_case_3')
                self.set_step_params('load_case_3', 'Drive', [500.0, -6.0])
                self.add_step('load_case_4')
                self.set_step_params('load_case_4', 'Drive', [500.0, -7.0])
                self.add_step('load_case_5')
                self.set_step_params('load_case_5', 'Drive', [500.0, -8.0])
                self.add_step('load_case_6')
                self.set_step_params('load_case_6', 'Drive', [500.0, -9.0])
                self.add_step('load_case_7')
                self.set_step_params('load_case_7', 'Drive', [500.0, -10.0])
                self.add_step('load_case_8')
                self.set_step_params('load_case_8', 'Drive', [500.0, -11.0])
                self.add_step('load_case_9')
                self.set_step_params('load_case_9', 'Drive', [500.0, -12.0])
                self.add_step('load_case_10')
                self.set_step_params('load_case_10', 'Drive', [500.0, -13.0])
                self.add_step('load_case_11')
                self.set_step_params('load_case_11', 'Drive', [500.0, -14.0])
                self.add_step('load_case_12')
                self.set_step_params('load_case_12', 'Drive', [500.0, -15.0])

        class MaterialsParams(morphopt.MaterialsParams):

            def __init__(self) -> None:
                super().__init__()

            def define_interface(self) -> None:

                self.add_interface(ForceMaterial(
                    material_parameters=self.models.NeoHookeanLnJParams(mu=0.482, kappa=4.8),
                    part_name='finger',
                    elementname='design',
                    mumax=0.482,
                    kappamax=4.8,
                    density=1.08e-09,
                    simp_ratio_min=1e-05,
                    initial_ratio=-0.6190392084062235,
                    voidpenalfactor=0.0001,
                    materialpenalty=8,
                    bounding_box=[2.0, 35.0, -1.0, 1.0, 0.0, 36.0],
                    simp_field_resolution=1.0,
                    degree=2,
                ), name='body')

                self.add_interface(morphopt.HomogeneousMaterial(
                    material_parameters=self.models.NeoHookeanLnJParams(mu=0.482, kappa=4.8),
                    part_name='finger',
                    elementname='solid',
                    density=1.08e-09,
                ), name='solid')

        def __init__(self) -> None:
            super().__init__(
                geometry=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialsParams()
            )

    class Solver(morphopt.Solver):

        def __init__(self, params: Any) -> None:

            super().__init__(params=params, num_process=1, process_devices=['cpu'], task_step_list=[['load_case_1', 'load_case_2', 'load_case_3', 'load_case_4', 'load_case_5', 'load_case_6', 'load_case_7', 'load_case_8', 'load_case_9', 'load_case_10', 'load_case_11', 'load_case_12']])

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
                self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=-15.0, threshold=0.0, p=4))
                self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=15.0, threshold=0.0, p=4))
                self.add_constraints(self.objectivefuncs.VolFrac(volfrac_min=0.7, volfrac_max=0.7, penalty=1000000.0, elementname='design'))
                self.if_update = True


if __name__ == "__main__":
    morphopt.start_optimization(device='cpu', restart_per_iteration=20)
