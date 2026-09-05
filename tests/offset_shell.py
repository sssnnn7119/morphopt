
import copy
import os
import tempfile
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'  # For environments where MKL causes issues. Adjust as needed.
import re
import numpy as np
import morphopt
import torch
import torchfea

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results/', 
                         opt_label='EXAMPLE')

        def objective_function(self):

            vol_fraction = self.get_volume_fraction()

            return self.fe_results[0].GC[-2]# + (vol_fraction - 0.4) ** 2 * 10

        def get_metrics(self):
            return [self.fe_results[0].GC[-2]]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.codesign.CodesignGeometry):

            def __init__(self):

                super().__init__(fea_seed_size=2.0, 
                                 mesh_order=2,
                                 reinitialize_per_iter=5,
                                 thickness=0.1,
                                 num_layers=2,)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=12.,
                                                    length=80.,
                                                    seed_size=1.0,
                                                    flip=False, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=12.))
 
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.0,
                                                flip=True,
                                                r0=6.,
                                                init_location=[0., 0., 40.],
                                                MaxC=1.5,
                    ))

            def apply_surface_constraints(self) -> None:
                """
                Apply the constraints (e.g. the surface constraint) of the surfaces.
                """
                a: ThisController.Params.GeometryParams.BSP = self.surface_list[0]
                cp0 = a._cps.reshape(a.model.size[0], a.model.size[1], 3)
                import torch
                cp0[:, :, 0] = (cp0[:, :, 0] + torch.flip(cp0[:, :, 0], dims=[1])) / 2
                cp0[:, :, 1] = (cp0[:, :, 1] - torch.flip(cp0[:, :, 1], dims=[1])) / 2
                cp0[:, :, 2] = (cp0[:, :, 2] + torch.flip(cp0[:, :, 2], dims=[1])) / 2


        class FEAParams(morphopt.codesign.CodesignFEAParams):

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_offset'),
                                        name='pressure_1')
                # self.add_fea_interface(self.ConcentratedForceInterface(rp_name='RP_head'), name='force_1')

            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(0, "pressure_1", [0.06])
                # self.set_step_params(0, "force_1", [1., 0., -0.])
                

        class MaterialParams(morphopt.codesign.CodesignMaterials):
            
            def __init__(self):
                super().__init__(mumax=4.82, 
                                 kappamax=48, 
                                 density=1.08e-9, 
                                 simp_ratio_min=0.001, 
                                 initial_ratio=0.01,
                                 bounding_box=[-15, 15, -15, 15, 0, 80], 
                                 simp_field_resolution=1.0, 
                                 degree=3,
                                 shell_mu=0.48,
                                 shell_kappa=4.8,
                                 shell_density=1.08e-9)
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(morphopt.Solver):
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
            super().__init__(surfaces=self.UpdaterGeometries(params=params),
                            materials=self.UpdaterMaterials(params=params),
                            *args, **kwargs)

        class UpdaterGeometries(morphopt.UpdaterGeometries):
            """
            Updater class for morphopt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self, params: morphopt.Params):

                super().__init__(
                    params=params,
                    max_step_iter=50)

                shape_derivative = self.objectivefuncs.ShapeDerivative()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[2.5, 2.5],
                                                                [2.5, 2.5]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=15., height=80., bottom=0.))
                
                self.add_constraints(morphopt.codesign.InwardCurvatureRadius(geometry=params.geometry))

                self.if_update = [False, True]

        class UpdaterMaterials(morphopt.UpdaterMaterials):
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
 

def _surface_orientation_and_volume(nodes_xyz: np.ndarray, tri: np.ndarray) -> tuple[float, float]:
    """
    Returns:
        oriented_volume: signed enclosed volume from oriented triangles
        consistency_ratio: fraction of triangle normals having same radial sign
    """
    a = nodes_xyz[tri[:, 0]]
    b = nodes_xyz[tri[:, 1]]
    c = nodes_xyz[tri[:, 2]]

    oriented_volume = float(np.einsum('ij,ij->i', a, np.cross(b, c)).sum() / 6.0)

    tri_center = (a + b + c) / 3.0
    center = tri_center.mean(axis=0, keepdims=True)
    face_normal = np.cross(b - a, c - a)
    radial_dot = np.einsum('ij,ij->i', face_normal, tri_center - center)

    positive = np.count_nonzero(radial_dot > 0)
    negative = np.count_nonzero(radial_dot < 0)
    consistency_ratio = max(positive, negative) / max(positive + negative, 1)
    return oriented_volume, float(consistency_ratio)


def validate_generated_inp() -> None:
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cpu')

    controller = ThisController()
    morphopt.controller = controller
    controller.initialize()

    try:
        temp_root = tempfile.gettempdir()

        with tempfile.TemporaryDirectory(prefix='cache_shell_verify_') as cache_dir:
            cache_dir_with_sep = os.path.join(cache_dir, '')
            part = controller.params.geometry.generate(path_result=cache_dir_with_sep, pools=controller.pools)

            part.surfaces.initialize(part)

            print('=== INP Validation (Shell Offset) ===')
            print(f'node count: {part.nodes.shape[0]}')
            print(f'element types: {list(part.elems.keys())}')
            fe = controller.params.feamodel.create_fea(part=part)
            fe.initialize()
            fe_part = fe.assembly.get_part("final_model")

            element_c3d4 = fe_part.elems.get('C3D4', None)
            element_c3d6 = fe_part.elems.get('C3D6', None)

            nodes = fe_part.nodes

            surfaceoffset = fe_part.surfaces.get_trimesh('surface_1_offset')

            surfnodes = nodes[surfaceoffset]
            surfnormals = torch.cross(
                surfnodes[:, 1] - surfnodes[:, 0],
                surfnodes[:, 2] - surfnodes[:, 0],
                dim=1
            )
            surfcenter = surfnodes.mean(dim=1)

            fe.assembly.get_instance('final_model').external_surface = 'surface_1_offset'

            print(f'from_inp elements: {list(fe_part.elems.keys())}')

        if 'C3D6' not in part.elems and 'C3D15' not in part.elems:
            raise RuntimeError("Shell wedge elements were not generated (expected 'C3D6' or 'C3D15').")
        
        element_c3d6.initialize(nodes=part.nodes)
        if element_c3d6.gaussian_weight.min() < 0:
            raise RuntimeError("Negative Gaussian weights found in C3D6 elements, which may lead to inaccurate results.")

        cavity_ids = []
        for name in part.surfaces.keys():
            m = re.fullmatch(r'surface_(\d+)_All', name)
            if m is not None and int(m.group(1)) >= 1:
                cavity_ids.append(int(m.group(1)))
        cavity_ids = sorted(set(cavity_ids))

        if len(cavity_ids) == 0:
            raise RuntimeError('No cavity surfaces surface_1_All.. found in generated inp.')

        print(f'cavity ids: {cavity_ids}')

        for cid in cavity_ids:
            offset_name = f'surface_{cid}_offset'
            if offset_name not in part.surfaces:
                raise RuntimeError(f'Missing offset surface definition: {offset_name} in part.surfaces')
            if offset_name not in part.set_nodes:
                raise RuntimeError(f'Missing offset node set: {offset_name} in part.set_nodes')

            tri = part.surfaces.get_trimesh(offset_name).detach().cpu().numpy().astype(int)
            if tri.size == 0:
                raise RuntimeError(f'Offset surface has empty triangles: {offset_name}')

            surf_items = part.surfaces[offset_name]
            if len(surf_items) == 0:
                raise RuntimeError(f'Offset surface has empty surface mapping: {offset_name}')

            print(f'{offset_name}: triangles={tri.shape[0]}, node_set={len(part.set_nodes[offset_name])}')

        # Check whether cavity surfaces are oriented and whether shell volume matches
        # enclosed-volume difference between surface_1_All and surface_1_offset.
        enclosed_diff_total = 0.0
        for cid in cavity_ids:
            tri_all = part.surfaces.get_trimesh(f'surface_{cid}_All').detach().cpu().numpy().astype(int)
            tri_offset = part.surfaces.get_trimesh(f'surface_{cid}_offset').detach().cpu().numpy().astype(int)

            nodes_xyz = part.nodes.detach().cpu().numpy()
            v_all_signed, orient_ratio_all = _surface_orientation_and_volume(nodes_xyz=nodes_xyz, tri=tri_all)
            v_offset_signed, orient_ratio_offset = _surface_orientation_and_volume(nodes_xyz=nodes_xyz, tri=tri_offset)

            print(f'surface_{cid}_All oriented volume: {v_all_signed:.6f}, orientation consistency: {orient_ratio_all:.4f}')
            print(f'surface_{cid}_offset oriented volume: {v_offset_signed:.6f}, orientation consistency: {orient_ratio_offset:.4f}')

            if orient_ratio_all < 0.95:
                raise RuntimeError(f'surface_{cid}_All is not well-oriented: consistency={orient_ratio_all:.4f}')
            if orient_ratio_offset < 0.95:
                raise RuntimeError(f'surface_{cid}_offset is not well-oriented: consistency={orient_ratio_offset:.4f}')

            enclosed_diff = abs(v_all_signed) - abs(v_offset_signed)
            if enclosed_diff <= 0:
                raise RuntimeError(
                    f'Enclosed volume is not reduced after offset for cavity {cid}: '
                    f'|V_all|-|V_offset|={enclosed_diff:.6f}'
                )
            enclosed_diff_total += enclosed_diff

        shell_elems = [elem for elem in fe_part.elems.values() if elem.__class__.__name__ in ['C3D6', 'C3D15']]
        if len(shell_elems) == 0:
            raise RuntimeError("No shell wedge elements found in assembly (expected C3D6/C3D15).")

        min_detj = float('inf')
        integrated_volume = 0.0
        for elem in shell_elems:
            # For current torchfea C3D6, base gauss weights are [0.5, 0.5],
            # and elem.gaussian_weight stores detJ * base_weight.
            # For C3D15, gaussian_weight is also detJ * base_weight; we only assert positivity.
            if elem.__class__.__name__ == 'C3D6':
                detj_now = (elem.gaussian_weight * 2.0).detach().cpu().numpy()
            else:
                detj_now = elem.gaussian_weight.detach().cpu().numpy()
            min_detj = min(min_detj, float(detj_now.min()))
            integrated_volume += float(elem.get_volumn().detach().cpu().item())

        if min_detj <= 0.0:
            raise RuntimeError(f'Found non-positive C3D6 Jacobian determinant at Gaussian points: min(detJ)={min_detj:.6e}')

        base_area = 0.0
        top_area = 0.0
        nodes_xyz = part.nodes.detach().cpu().numpy()
        for cid in cavity_ids:
            tri_base = part.surfaces.get_trimesh(f'surface_{cid}_All').detach().cpu().numpy().astype(int)
            a = nodes_xyz[tri_base[:, 0]]
            b = nodes_xyz[tri_base[:, 1]]
            c = nodes_xyz[tri_base[:, 2]]
            base_area += float((0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)).sum())

            tri_top = part.surfaces.get_trimesh(f'surface_{cid}_offset').detach().cpu().numpy().astype(int)
            a = nodes_xyz[tri_top[:, 0]]
            b = nodes_xyz[tri_top[:, 1]]
            c = nodes_xyz[tri_top[:, 2]]
            top_area += float((0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)).sum())

        thickness_total = float(controller.params.geometry.shell_thickness)
        volume_area_thickness = base_area * thickness_total
        volume_area_avg = 0.5 * (base_area + top_area) * thickness_total
        rel_err_simple = abs(integrated_volume - volume_area_thickness) / max(abs(volume_area_thickness), 1e-12)
        rel_err_avg = abs(integrated_volume - volume_area_avg) / max(abs(volume_area_avg), 1e-12)

        print(f'C3D6 Jacobian check: min(detJ)={min_detj:.6e} (>0)')
        print(f'C3D6 volume by gaussian integration: {integrated_volume:.6f}')
        print(f'C3D6 volume by enclosed-surface difference: {enclosed_diff_total:.6f}')
        print(f'C3D6 volume by area*thickness: {volume_area_thickness:.6f}')
        print(f'C3D6 volume(simple) relative error: {rel_err_simple:.6%}')
        print(f'C3D6 volume by avg-area*thickness: {volume_area_avg:.6f}')
        print(f'C3D6 volume(avg-area) relative error: {rel_err_avg:.6%}')

        rel_err_enclosed = abs(integrated_volume - enclosed_diff_total) / max(abs(enclosed_diff_total), 1e-12)
        print(f'C3D6 volume(enclosed-diff) relative error: {rel_err_enclosed:.6%}')

        if rel_err_enclosed > 0.08:
            raise RuntimeError(
                'C3D6 volume mismatch is too large compared with enclosed surface-volume difference: '
                f'rel_err_enclosed={rel_err_enclosed:.6%}'
            )

        # For inward offsets with area contraction, average-area estimate is a tighter sanity check.
        if rel_err_avg > 0.20:
            raise RuntimeError(
                'C3D6 volume mismatch is too large compared with avg-area*thickness estimate: '
                f'rel_err_avg={rel_err_avg:.6%}'
            )

        print('Validation passed.')
    finally:
        if controller.pools is not None:
            controller.pools.close()
            controller.pools.join()


if __name__ == '__main__':
    validate_generated_inp()

