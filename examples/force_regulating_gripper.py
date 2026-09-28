"""Density optimization of one symmetric half of a force-regulating gripper.

Units: mm, N, MPa. A single fixed finger and a 32 mm rigid cylinder represent
one symmetric half of a parallel gripper. The cylinder is progressively
closed; the objective tracks a constant contact force over the working stroke.
The pad uses one C3D8 element layer through its thickness with zero transverse
displacement, giving a plane-strain approximation. Contact is frictionless.
This model calibrates contact force; it does not simulate a lift.
The dimensions, material and 3 N target are starting values, not validated data.
"""

import numpy as np
import torch
import torchfea

import morphopt

mu_material = 0.482
kappa_material = 4.8
minratio = 1e-5
mesh_size = 0.5
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
closure_steps = np.arange(0.0, 20.0 + 0.5, 1.0).tolist()
working_stroke_start = 10.0  # mm of commanded closure; contact begins near 4 mm.
target_force = 3.0  # Per finger; not the cancelling pair resultant.
initial_density = 0.35
volume_fraction_max = (
    0.7  # Existing fixed-volume setting (min=max); design region only.
)
drive_stiffness = 1e2  # N/mm; track displacement error in the metrics.
contact_distance = 3.0  # Smooth-contact support; refine with the mesh.


def _build_finger_part():
    """Conforming bricks: exact solid/design interfaces with shared nodes."""

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
    # One C3D8 layer through thickness, as in the 2D-style gripper model.
    y = np.array([-finger_width / 2, finger_width / 2])
    z = coordinates(-finger_height / 2, finger_height / 2)
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
    part.add_surface_set("extern", exterior)
    part.add_surface_set("contact", contact)
    return part


class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(
            path_result_folder=".results/", opt_label="ForceRegulatingGripper"
        )

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def get_force_displacement(self, stepidx):
            self.set_step(stepidx)
            assembly = self.fe.assembly
            rgc = assembly._GC2RGC(self.fe_results[stepidx].GC)
            rp = assembly.get_reference_point("RPCylinder")
            displacement = rgc[rp._RGC_index].reshape(-1)[0]
            drive = assembly.get_load("Drive")
            # Positive compressive contact reaction, inferred from the drive
            # spring at equilibrium. Do not abs()/clamp() the sign or detach AD.
            force = drive.k * (displacement - drive.target)
            return force, -displacement

        def objective_function(self):
            """J = (1/L) integral [(F(s) / target_force - 1)^2] ds."""
            # Keep working_stroke_start in closure_steps when refining the load grid.
            start = closure_steps.index(working_stroke_start)
            forces = torch.stack(
                [
                    self.get_force_displacement(stepidx)[0]
                    for stepidx in range(start, len(closure_steps))
                ]
            )
            closures = forces.new_tensor(closure_steps[start:])
            error = ((forces - target_force) / target_force).square()
            return torch.trapezoid(error, closures) / (closures[-1] - closures[0])

        def get_volume_fraction(self):
            material = morphopt.controller.params.materials.interfaces["body"]
            part = self.fe.assembly.get_part("finger")
            elems = part.elems["design"]
            points = elems.get_gaussian_points(part.nodes).reshape(-1, 3)
            rho = torch.sigmoid(material._map_bsp_designfield(points)).flatten()
            weights = elems.gaussian_weight.flatten()
            return (rho * weights).sum() / weights.sum()

        def get_metrics(self):
            # Full force-displacement trace, drive errors [mm], and volume fraction.
            forces, errors = [], []
            for stepidx in range(len(closure_steps)):
                force, closure = self.get_force_displacement(stepidx)
                forces.append(force)
                errors.append(closure_steps[stepidx] - closure)
            return forces + errors + [self.get_volume_fraction()]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):
            class GripperPart(morphopt.BasePartInterface):
                cache_part = True

                def define_instance(self):
                    self.add_instance(self.part_name, "finger", [0, 0, 0, 0, 0, 0])

                def build_part(self, path_result=None, pools=None):
                    return _build_finger_part()

            class CylinderPart(morphopt.BasePartInterface):
                cache_part = True

                def __init__(self):
                    super().__init__(exterior_surface="extern")

                def build_part(self, path_result=None, pools=None):
                    cad = torchfea.cad.CADModel()
                    history = cad.add_part(self.part_name)
                    # The cylinder axis is explicitly parallel to the finger
                    # thickness (global y); its center is at y=0, matching the
                    # single-layer plane-strain finger.
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

            def define_interface(self):
                self.add_interface(
                    self.GripperPart(exterior_surface="extern"), name="finger"
                )
                self.add_interface(self.CylinderPart(), name="cylinder")

        class FEAParams(morphopt.FEAParams):
            def define_interface(self):
                self.add_interface(
                    self.BoundaryConditionInterface(
                        instance_name="finger",
                        set_nodes_name="root",
                        index_dof=[0, 2],
                    ),
                    name="Root",
                )
                self.add_interface(
                    self.BoundaryConditionInterface(
                        instance_name="finger",
                        set_nodes_name="all",
                        index_dof=[1],
                    ),
                    name="BC_PlaneStrain",
                )
                self.add_interface(
                    self.ReferencePointInterface(
                        rp_location=[finger_depth + initial_gap / 2, 0, 0]
                    ),
                    name="RPCylinder",
                )
                self.add_interface(
                    self.CoupleInterface(
                        rp_name="RPCylinder",
                        instance_name="cylinder",
                        set_nodes_name="all",
                    ),
                    name="RigidCylinder",
                )
                self.add_interface(
                    self.BoundaryConditionRPInterface(
                        rp_name="RPCylinder", index_dof=[1, 2, 3, 4, 5]
                    ),
                    name="CylinderGuide",
                )
                self.add_interface(
                    self.PenaltyDoFInterface(obj_name="RPCylinder", s=0), name="Drive"
                )
                self.add_interface(
                    self.ContactInterface(
                        instance_name1="finger",
                        surface_name1="contact",
                        instance_name2="cylinder",
                        surface_name2="extern",
                        penalty_threshold_h=contact_distance,
                    ),
                    name="Contact",
                )

            def define_steps(self):
                self.set_step_num(len(closure_steps))
                for stepidx, closure in enumerate(closure_steps):
                    self.set_step_params(
                        step_index=stepidx,
                        load_name="Drive",
                        values=[drive_stiffness, -closure],
                    )

        class MaterialsParams(morphopt.MaterialsParams):
            def define_interface(self):
                material = self.materialmodels.NeoHookeanLnJParams(
                    mu=mu_material, kappa=kappa_material
                )
                self.add_interface(
                    ThisController.Params.BodyMaterial(material), name="body"
                )
                self.add_interface(
                    self.HomogeneousMaterial(
                        part_name="finger",
                        elementname="solid",
                        material_parameters=material,
                        density=1.08e-9,
                    ),
                    name="solid",
                )

        class BodyMaterial(morphopt.SIMP_BSPFieldMaterials):
            def __init__(self, material_parameters):
                super().__init__(
                    mumax=mu_material,
                    kappamax=kappa_material,
                    density=1.08e-9,
                    initial_ratio=float(
                        np.log(initial_density / (1 - initial_density))
                    ),
                    simp_ratio_min=minratio,
                    bounding_box=[
                        root_depth,
                        finger_depth - skin_depth,
                        -simp_field_thickness / 2,
                        simp_field_thickness / 2,
                        -finger_height / 2,
                        finger_height / 2,
                    ],
                    simp_field_resolution=field_resolution,
                    degree=simp_degree,
                    material_parameters=material_parameters,
                    voidpenalfactor=0.0,
                    elementname="design",
                    part_name="finger",
                )
                # Keep MorphOpt's existing RAMP stiffness interpolation. The
                # volume constraint uses sigmoid(field), not stiffness scale.

            def update_variables(self, x_change, max_step_length=None):
                """Keep updates uniform through thickness and symmetric in height."""
                nx, ny, nz = self._bsp_size
                x_change_3d = x_change.reshape(nx, ny, nz)
                x_change_3d = x_change_3d.mean(dim=1, keepdim=True).expand(nx, ny, nz)
                x_change_3d = 0.5 * (x_change_3d + x_change_3d.flip(dims=[2]))
                if isinstance(max_step_length, list):
                    max_step_length = max_step_length[0]
                if max_step_length is not None and max_step_length.numel() > 1:
                    max_step_length = max_step_length.reshape(nx, ny, nz)
                    max_step_length = max_step_length.mean(dim=1, keepdim=True).expand(
                        nx, ny, nz
                    )
                    max_step_length = 0.5 * (
                        max_step_length + max_step_length.flip(dims=[2])
                    )
                if max_step_length is None:
                    max_step_length = torch.ones_like(self._cps)
                if max_step_length.numel() > 1:
                    max_step_length = max_step_length.reshape_as(self._cps)
                max_step_length = max_step_length.to(self._cps.device)
                # atan(x) is algebraically identical to atan(abs(x))*sign(x),
                # but also gives the correct nonzero derivative at x=0 in AD.
                self._cps = self._cps.detach() + (
                    (2.0 / torch.pi)
                    * torch.atan(x_change_3d.reshape_as(self._cps))
                    * max_step_length
                )

            def get_meshes(self):
                """Show the full 2D finger, including its solid end regions."""
                xmin, xmax, _ymin, _ymax, zmin, zmax = self._bounding_box
                nx, _ny, nz = self._bsp_size

                import numpy as np
                import pyvista as pv

                nx_design_q = max(2, (nx - 1) * 2 + 1)
                nz_q = max(2, (nz - 1) * 2 + 1)
                dx_visual = (xmax - xmin) / max(nx_design_q - 1, 1)
                x_parts = []
                if xmin > 0:
                    nx_root_q = max(1, int(np.ceil(xmin / dx_visual)))
                    x_parts.append(np.linspace(0.0, xmin, nx_root_q + 1)[:-1])
                x_parts.append(np.linspace(xmin, xmax, nx_design_q))
                if xmax < finger_depth:
                    nx_tip_q = max(1, int(np.ceil((finger_depth - xmax) / dx_visual)))
                    x_parts.append(np.linspace(xmax, finger_depth, nx_tip_q + 1)[1:])
                xq = np.concatenate(x_parts)
                nx_q = len(xq)
                yq = np.array([0.0])
                zq = np.linspace(zmin, zmax, nz_q)
                xg, yg, zg = np.meshgrid(xq, yq, zq, indexing="ij")
                points = np.column_stack(
                    [axis.reshape(-1, order="F") for axis in (xg, yg, zg)]
                )

                design_mask = (xg[:, 0, :] >= xmin) & (xg[:, 0, :] <= xmax)
                design_mask_flat = design_mask.flatten(order="F")
                designfield = self._map_bsp_designfield(
                    torch.as_tensor(
                        points[design_mask_flat],
                        device=torch.get_default_device(),
                        dtype=torch.get_default_dtype(),
                    )
                )
                design_ratio = (
                    self.get_material_ratio(designfield)
                    .detach()
                    .cpu()
                    .numpy()
                    .reshape(-1)
                )
                density = np.full((nx_q, nz_q), self._mumax, dtype=float)
                density_flat = density.flatten(order="F")
                density_flat[design_mask_flat] = (
                    np.clip(design_ratio, 0.0, 1.0) * self._mumax
                )
                face_count = (nx_q - 1) * (nz_q - 1)
                faces = np.empty((face_count, 5), dtype=np.int64)
                cell = 0
                for k in range(nz_q - 1):
                    for i in range(nx_q - 1):
                        lower_left = i + nx_q * k
                        faces[cell] = (
                            4,
                            lower_left,
                            lower_left + 1,
                            lower_left + nx_q + 1,
                            lower_left + nx_q,
                        )
                        cell += 1
                surface = pv.PolyData(points, faces.reshape(-1))
                surface.point_data["density"] = density_flat
                return [surface]

            def plot(self, plotter=None, meshes=None):
                """Render every 2D cell without the base class density threshold."""
                import numpy as np
                import pyvista as pv

                if plotter is None:
                    plotter = pv.Plotter(window_size=(1400, 1000))
                if meshes is None:
                    surface = self.get_meshes()[0]
                elif isinstance(meshes, (list, tuple)):
                    surface = next(
                        (mesh for mesh in meshes if "density" in mesh.point_data),
                        self.get_meshes()[0],
                    )
                else:
                    surface = meshes

                values = np.asarray(surface.point_data["density"])
                finite_values = values[np.isfinite(values)]
                if finite_values.size == 0:
                    return plotter
                lower = float(finite_values.min())
                upper = float(finite_values.max())
                if np.isclose(lower, upper):
                    padding = max(abs(lower) * 0.05, self._mumax * 0.01)
                    color_limits = (lower - padding, upper + padding)
                else:
                    color_limits = (lower, upper)

                plotter.add_mesh(
                    surface,
                    scalars="density",
                    cmap="viridis",
                    clim=color_limits,
                    show_edges=False,
                    lighting=False,
                    scalar_bar_args={"title": "Material scale"},
                )
                return plotter

            def reinitialize(self, iteration, *args, **kwargs):
                nx, ny, nz = self._bsp_size
                control_points = self._cps.reshape(nx, ny, nz)
                control_points = (
                    control_points.mean(dim=1, keepdim=True).expand(nx, ny, nz).clone()
                )
                control_points = 0.5 * (control_points + control_points.flip(dims=[2]))
                # Keep the design field invariant through the single-layer
                # thickness; the solid contact skin is defined geometrically.
                self._cps = control_points.reshape_as(self._cps)
                super().reinitialize(iteration, *args, **kwargs)

        def __init__(self):
            super().__init__(
                geometry=self.GeometryParams(),
                feamodel=self.FEAParams(),
                materials=self.MaterialsParams(),
            )

    class Solver(morphopt.Solver):
        def __init__(self, params):
            super().__init__(
                params=params,
                available_gpus=["cuda"],
                num_process=1,
                task_index_list=[list(range(len(closure_steps)))],
            )

        def _previous_solution(self):
            # Repeat loading from the undeformed configuration each iteration.
            # Within this group, the base solver continues from the last step.
            return None

    class Updater(morphopt.Updaters):
        def __init__(self, params):
            super().__init__(params=params, device="cpu")

        def define_updater(self):
            self.add_material_updater(self.UpdaterSIMPMaterial(), name="body")

        class UpdaterSIMPMaterial(morphopt.UpdaterSIMPMaterial):
            def __init__(self):
                super().__init__(max_step_iter=100)

            def define_objective(self):
                self.add_objective_function(
                    self.objectivefuncs.Sensitivity(normalize_gradient=False)
                )
                self.add_constraints(
                    self.objectivefuncs.boundarys.MinValue(xmin=-15, threshold=0.0, p=4)
                )
                self.add_constraints(
                    self.objectivefuncs.boundarys.MaxValue(xmax=15, threshold=0.0, p=4)
                )
                self.add_constraints(
                    self.objectivefuncs.VolFrac(
                        volfrac_min=volume_fraction_max,
                        volfrac_max=volume_fraction_max,
                        penalty=1e6,
                        elementname="design",
                    )
                )
                self.if_update = True


if __name__ == "__main__":
    morphopt.start_optimization(device="cpu", restart_per_iteration=20)
