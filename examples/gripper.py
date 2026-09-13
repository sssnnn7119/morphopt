import numpy as np
import torch
import torchfea

import morphopt

mumax = 10.0
minratio = 1e-7
cylinder_x = [80.0, 70.0, 60.0, 50.0]


def _surface_at_coordinate(
        part: torchfea.Part,
        element_name: str,
        axis: int,
        coordinate: float,
        tolerance: float = 1e-8,
) -> list[tuple[np.ndarray, int]]:
    """Return boundary faces whose nodes lie on one coordinate plane."""
    element = part.elems[element_name]
    selected: list[tuple[np.ndarray, int]] = []
    for element_ids, side in element.extract_boundary_surface_set():
        element_ids_array = np.asarray(element_ids, dtype=np.int64)
        element_ids_tensor = torch.as_tensor(
            element_ids_array, dtype=torch.long, device=element._elems.device)
        face_nodes = element._elems[
            element_ids_tensor][:, element.surfaceid_map[int(side)]]
        face_coordinates = part.nodes[face_nodes][..., axis]
        on_plane = (face_coordinates - float(coordinate)).abs().amax(dim=1)
        matching_ids = element_ids_array[
            (on_plane <= tolerance).detach().cpu().numpy()]
        if len(matching_ids):
            selected.append((matching_ids, int(side)))
    if not selected:
        raise RuntimeError(
            f"No boundary faces found on axis {axis}={coordinate}.")
    return selected


def _add_gripper_sets(part: torchfea.Part) -> None:
    """Recreate the named sets used by the gripper loads and contacts."""
    element_name = "C3D4"
    xmin_nodes = torch.where((part.nodes[:, 0] - 0.0).abs() <= 1e-8)[0]
    if not xmin_nodes.numel():
        raise RuntimeError("No gripper nodes found on x=0.")
    part.add_node_set("nodes_xmin", xmin_nodes)
    part.add_surface_set(
        "surface_zmax",
        _surface_at_coordinate(part, element_name, axis=2, coordinate=0.0),
    )
    part.add_surface_set("surface_0_All", list(part.surfaces["extern"]))
    part.exterior_surface = "surface_0_All"


class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(
            path_result_folder=".results/",
            opt_label="Gripper",
        )

    class ObjectiveFunction(morphopt.simp.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def get_volume_fraction(self):
            elems = self.fe.assembly._parts["final_model"].elems["C3D4"]

            materials = elems.materials

            ratio_now = materials["material-0"].scale
            gaussian_weight = elems.gaussian_weight  # [gaussian, element]

            volume = gaussian_weight * ratio_now
            volume_total = gaussian_weight.sum()

            volume_fraction = volume.sum() / volume_total

            return volume_fraction

        def objective_function(self):

            loss_list = []
            for stepidx in range(self.num_tasks):
                self.set_step(stepidx)
                total_force = self.fe.assembly._assemble_generalized_Matrix(
                    GC=self.fe_results[stepidx].GC
                )[0]

                ins_gripper = self.fe.assembly.get_instance("final_model")
                RGC_index_start = self.fe.assembly._RGC_list_indexStart

                force_gripper = total_force[
                    RGC_index_start[ins_gripper._RGC_index] : RGC_index_start[
                        ins_gripper._RGC_index + 1
                    ]
                ].reshape([-1, 3])
                loss_now = (
                    torch.exp(force_gripper[:, 0].sum()) - force_gripper[:, 2].sum()
                )
                loss_list.append(loss_now)

            return torch.stack(loss_list).sum()

        def get_metrics(self):

            metrics_list = []
            for stepidx in range(self.num_tasks):
                self.set_step(stepidx)
                total_force = self.fe.assembly._assemble_generalized_Matrix(
                    GC=self.fe_results[stepidx].GC
                )[0]

                ins_gripper = self.fe.assembly.get_instance("final_model")
                RGC_index_start = self.fe.assembly._RGC_list_indexStart

                force_gripper = total_force[
                    RGC_index_start[ins_gripper._RGC_index] : RGC_index_start[
                        ins_gripper._RGC_index + 1
                    ]
                ].reshape([-1, 3])
                metrics_list.append(force_gripper[:, 0].sum())
                metrics_list.append(force_gripper[:, 2].sum())

            return metrics_list + [self.get_volume_fraction()]

    class Params(morphopt.simp.Params):
        class GeometryParams(morphopt.simp.FixedGeometry):
            def define_assembly(self):
                box_cad = torchfea.cad.CADModel()
                box_history = box_cad.add_part("final_model")
                box_history.add_box(
                    x=0.0, y=-0.5, z=-30.0,
                    dx=80.0, dy=1.0, dz=30.0,
                )
                part = box_cad.mesh_part("final_model", mesh_size=0.5)
                _add_gripper_sets(part)

                instance = torchfea.Instance(part_name="final_model")
                assembly = torchfea.Assembly()
                assembly.add_part(part, name="final_model")
                assembly.add_instance(instance, name="final_model")
                instance.exterior_surface = "surface_0_All"

                cylinder_cad = torchfea.cad.CADModel()
                cylinder_history = cylinder_cad.add_part("cylinder")
                cylinder_history.add_cylinder(
                    x=80.0, y=-10.0, z=15.0,
                    dy=20.0, radius=15.0,
                )
                part_cylinder = cylinder_cad.mesh_part(
                    "cylinder", mesh_size=1.5)
                part_cylinder.add_node_set(
                    "cylinder", part_cylinder.set_nodes["all"])

                assembly.add_part(part_cylinder, name="cylinder")

                for i in range(len(cylinder_x)):
                    instance_cylinder = torchfea.Instance(
                        part_name="cylinder", translation=[cylinder_x[i] - 80, 0.0, 0.0]
                    )
                    assembly.add_instance(
                        instance_cylinder, name=f"cylinder{cylinder_x[i]}"
                    )
                    instance_cylinder.exterior_surface = "extern"
                return assembly

        class FEAParams(morphopt.simp.FEAParams):
            def define_interface(self) -> None:
                # Boundary the xmin as base
                self.add_fea_interface(
                    self.ReferencePointInterface(rp_location=[0.0, 0.0, 0.0]),
                    name="RPBase",
                )
                self.add_fea_interface(
                    self.CoupleInterface(
                        rp_name="RPBase",
                        instance_name="final_model",
                        set_nodes_name="nodes_xmin",
                    )
                )
                self.add_fea_interface(
                    self.BoundaryConditionRPInterface(
                        rp_name="RPBase", index_dof=[0, 1, 2, 3, 4, 5]
                    ),
                    name="BC_RPBase",
                )

                # Boundary the xmax as base
                # self.add_fea_interface(self.ReferencePointInterface(rp_location=[80., 0., -15.]), name='RPXmax')
                # self.add_fea_interface(self.CoupleInterface(rp_name='RPXmax', instance_name='final_model', set_nodes_name='nodes_xmax'))

                # Symmetry boundary condition at the middle plane (y=0)
                self.add_fea_interface(
                    self.BoundaryConditionInterface(
                        instance_name="final_model", set_nodes_name="all", index_dof=[1]
                    ),
                    name="BC_Symmetry",
                )

                # Rigid cylinder
                for i in range(len(cylinder_x)):
                    self.add_fea_interface(
                        self.ReferencePointInterface(
                            rp_location=[cylinder_x[i], 0.0, 15.0]
                        ),
                        name=f"RPCylinder{cylinder_x[i]}",
                    )
                    self.add_fea_interface(
                        self.CoupleInterface(
                            rp_name=f"RPCylinder{cylinder_x[i]}",
                            instance_name=f"cylinder{cylinder_x[i]}",
                            set_nodes_name="cylinder",
                        )
                    )
                    self.add_fea_interface(
                        self.BoundaryConditionRPInterface(
                            rp_name=f"RPCylinder{cylinder_x[i]}",
                            index_dof=[0, 1, 3, 4, 5],
                        ),
                        name=f"BC_RPCylinder{cylinder_x[i]}",
                    )
                    self.add_fea_interface(
                        self.PenaltyDoFInterface(
                            obj_name=f"RPCylinder{cylinder_x[i]}", s=2
                        ),
                        name=f"Penalty_RPCylinder{cylinder_x[i]}_Z",
                    )

                    # Contact between the cylinder and the gripper
                    self.add_fea_interface(
                        self.ContactInterface(
                            instance_name1="final_model",
                            surface_name1="surface_zmax",
                            instance_name2=f"cylinder{cylinder_x[i]}",
                            surface_name2="extern",
                        ),
                        name=f"Contact_Gripper_Cylinder{cylinder_x[i]}",
                    )

            def define_steps(self):
                self.set_step_num(len(cylinder_x))
                for stepidx in range(len(cylinder_x)):
                    for cylinderidx in range(len(cylinder_x)):
                        self.set_step_params(
                            step_index=stepidx,
                            load_name=f"Penalty_RPCylinder{cylinder_x[cylinderidx]}_Z",
                            values=[1e2, -10.0]
                            if cylinderidx == stepidx
                            else [1e2, 0.0],
                        )

        class MaterialsParams(morphopt.simp.MaterialsParams):

            class BodyMaterial(morphopt.simp.SIMP_BSPFieldMaterials):
                def reinitialize(self, iteration, *args, **kwargs):
                    cps_reshaped = self._cps.reshape(
                        self._bsp_size[0], self._bsp_size[1], self._bsp_size[2]
                    )

                    cps_reshaped[:, :, -2:] = 15.0

                    self._cps = cps_reshaped.reshape_as(self._cps)

                    super().reinitialize(iteration, *args, **kwargs)

                def get_meshes(self):
                    xmin, xmax, ymin, ymax, zmin, zmax = self._bounding_box
                    nx, ny, nz = self._bsp_size
                    import numpy as np
                    import pyvista as pv

                    # Sample at the BSP control-point resolution × 2 for smooth rendering
                    nx_q = max(2, (nx - 1) * 2 + 1)
                    ny_q = 1
                    nz_q = max(2, (nz - 1) * 2 + 1)

                    xq = np.linspace(xmin, xmax, nx_q)
                    yq = np.array([0.0])
                    zq = np.linspace(zmin, zmax, nz_q)
                    xg, yg, zg = np.meshgrid(xq, yq, zq, indexing="ij")
                    pts_query = np.stack([xg, yg, zg], axis=-1).reshape(-1, 3)

                    designfield = self._map_bsp_designfield(
                        torch.from_numpy(pts_query)
                        .to(torch.get_default_device())
                        .to(torch.get_default_dtype())
                    )
                    ratio_query = (
                        self.get_material_ratio(designfield)
                        .reshape(nx_q, ny_q, nz_q)
                        .cpu()
                        .numpy()
                    )
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
                    grid.point_data["density"] = ratio_grid.flatten(order="F") * self._mumax

                    return [grid]

            def define_interface(self) -> None:
                self.add_material_interface(
                    self.BodyMaterial(
                        material_parameters=self.materialmodels.NeoHookeanLnJParams(
                            mu=mumax, kappa=mumax * 10),
                        mumax=mumax,
                        kappamax=mumax * 10,
                        density=1.08e-9,
                        initial_ratio=-2.0,
                        simp_ratio_min=minratio,
                        bounding_box=[0.0, 80.0, -1.0, 1.0, -30.0, 0.0],
                        simp_field_resolution=1.0,
                        degree=2,
                        voidpenalfactor=0e-2,
                        elementname="C3D4",
                        part_name="final_model",
                    ),
                    name="body")

        def __init__(self):
            super().__init__(
                surfaces=self.GeometryParams(),
                feamodel=self.FEAParams(),
                materials=self.MaterialsParams(),
            )

    class Solver(morphopt.simp.SIMPSolver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.simp.Params):

            super().__init__(params=params, available_gpus=["cuda:0"], num_process=1)

    class Updater(morphopt.simp.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: morphopt.simp.Params, *args, **kwargs):
            super().__init__(
                materials=self.UpdaterMaterials(params=params),
                device="cpu",
                *args,
                **kwargs,
            )

        class UpdaterMaterials(morphopt.simp.UpdaterMaterials):
            """
            Material updater based on SIMP control points.
            """

            def __init__(self, params: morphopt.simp.Params):
                super().__init__(
                    params=params,
                    max_step_iter=100,
                )

                shape_derivative = self.objectivefuncs.Sensitivity(
                    normalize_gradient=False
                )
                self.add_objective_function(shape_derivative)

                # density_regularization = self.objectivefuncs.DensityFieldMinimize(scale=1e-7)
                # self.add_objective_function(density_regularization)

                # Keep SIMP control points within [0, 1] and avoid singular material values.
                self.add_constraints(
                    self.objectivefuncs.boundarys.MinValue(xmin=-15, threshold=0.0, p=2)
                )
                self.add_constraints(
                    self.objectivefuncs.boundarys.MaxValue(xmax=15, threshold=0.0, p=2)
                )

                self.add_constraints(
                    self.objectivefuncs.VolFrac(
                        volfrac_min=0.3,
                        volfrac_max=0.4,
                        penalty=1e6,
                        elementname="C3D4",
                    )
                )

                self.if_update = True


if __name__ == "__main__":
    morphopt.start_optimization(device="cpu", restart_per_iteration=20)
