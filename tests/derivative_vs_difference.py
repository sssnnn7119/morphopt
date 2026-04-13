
import copy
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'  # For environments where MKL causes issues. Adjust as needed.
import morphopt
import torch
import torchfea


# Tunable derivative-check parameters
N_GEOM_CHECK = 4
N_MAT_CHECK = 4
FD_EPS = 1e-4
MIN_GRAD_ABS = 1e-10


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

            mu = materials._mu
            gaussian_weight = elems.gaussian_weight  # [gaussian, element]

            ratio_now = (mu - mumax * minratio) / (mumax * (1 - minratio))
            ratio_now = ratio_now.clamp(0.0, 1.0)

            volume = gaussian_weight * ratio_now
            volume_total = gaussian_weight.sum()

            volume_fraction = volume.sum() / volume_total

            return volume_fraction

        def objective_function(self):


            return self.fe_results[0].GC[-2]# + (vol_fraction - 0.4) ** 2 * 10

        def get_metrics(self):
            return [self.fe_results[0].GC[-2]]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.codesign.CodesignGeometry):

            def __init__(self):

                super().__init__(fea_seed_size=1.2, 
                                 fea_mesh_order=1, 
                                 reinitialize_per_iter=5,
                                 thickness=1.5,
                                 num_layers=2,)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=12.,
                                                    length=80.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
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
                Apply the constraints (e.g. the symmetric constraint) of the surfaces.
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
                                 simp_ratio_min=0.01, 
                                 initial_ratio=0.01,
                                 bounding_box=[-15, 15, -15, 15, 0, 80], 
                                 simp_field_resolution=1.0, 
                                 degree=3,
                                 shell_mu=0.48,
                                 shell_kappa=4.8,
                                 shell_density=1.08e-9)
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(morphopt.MorphSolver):
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
                    max_step_iter=100)

                shape_derivative = self.objectivefuncs.ShapeDerivative()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[2.5, 2.5],
                                                                [2.5, 2.0]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=15., height=80., bottom=0.))
                
                self.add_constraints(morphopt.codesign.InwardCurvatureRadius(geometry=params.geometry))
                self.add_constraints(morphopt.codesign.OffsetSurfaceMinThickness(geometry=params.geometry, min_distance=2.0))

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


def run_once(
    controller: ThisController,
    fe_template: torchfea.FEAController,
    design_vars: dict[str, torch.Tensor],
) -> torch.Tensor:
    # Reuse one FE template and only deep-copy it to avoid remeshing each FD probe.
    fe = copy.deepcopy(fe_template)
    controller.params.modify_assembly(design_vars, fe.assembly)
    fe.initialize()
    controller.objfun.fe = fe
    controller.objfun.fe_results = controller.solver.solve()
    controller.objfun.build_objective_functions()
    return controller.objfun.get_objective().detach()


def central_difference(
    controller: ThisController,
    fe_template: torchfea.FEAController,
    x0_full: dict[str, torch.Tensor],
    key: str,
    sampled_ids: torch.Tensor,
    eps: float = 1e-4,
) -> torch.Tensor:
    grad_fd = torch.zeros(sampled_ids.numel(), dtype=x0_full[key].dtype, device=x0_full[key].device)
    for i, idx in enumerate(sampled_ids):
        xp_dict = {k: v.clone() for k, v in x0_full.items()}
        xm_dict = {k: v.clone() for k, v in x0_full.items()}
        xp_dict[key][idx] += eps
        xm_dict[key][idx] -= eps

        fp = run_once(controller, fe_template, xp_dict)
        fm = run_once(controller, fe_template, xm_dict)
        grad_fd[i] = (fp - fm) / (2.0 * eps)
    return grad_fd


def sample_ids(total_numel: int, count: int, device: torch.device) -> torch.Tensor:
    if count >= total_numel:
        return torch.arange(total_numel, device=device, dtype=torch.long)
    return torch.linspace(0, total_numel - 1, steps=count, device=device).round().long().unique()


def sample_ids_by_gradient(
    grad_full: torch.Tensor,
    count: int,
    min_abs: float,
) -> torch.Tensor:
    grad_abs = grad_full.detach().abs().flatten()
    if grad_abs.numel() == 0:
        return torch.zeros(0, dtype=torch.long, device=grad_abs.device)

    candidate = torch.nonzero(grad_abs > min_abs, as_tuple=False).flatten()
    if candidate.numel() > 0:
        cand_vals = grad_abs[candidate]
        k = min(count, candidate.numel())
        top_local = torch.topk(cand_vals, k=k, largest=True, sorted=True).indices
        return candidate[top_local]

    # Fallback: all gradients are very small, still return top-k by magnitude.
    k = min(count, grad_abs.numel())
    return torch.topk(grad_abs, k=k, largest=True, sorted=True).indices


def main():
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cpu')

    controller = ThisController()
    morphopt.controller = controller
    controller.initialize()

    try:
        fe0 = controller.params.create_feamodel(path_result='Z:/cache/', pools=controller.pools)
        x0_full = {
            key: value.detach().clone()
            for key, value in controller.params.obtain_design_sensitivity_vars(fe0.assembly).items()
        }

        geom_key = 'geometry'
        mat_key = 'materials'

        controller.objfun.fe = copy.deepcopy(fe0)
        controller.objfun.fe_results = controller.solver.solve()
        grad_ad_dict = {
            key: value.detach()
            for key, value in controller.objfun.sensitivity_analysis(controller.params).items()
        }

        geom_ids = sample_ids_by_gradient(
            grad_full=grad_ad_dict[geom_key],
            count=N_GEOM_CHECK,
            min_abs=MIN_GRAD_ABS,
        )
        mat_ids = sample_ids_by_gradient(
            grad_full=grad_ad_dict[mat_key],
            count=N_MAT_CHECK,
            min_abs=MIN_GRAD_ABS,
        )

        for key, ids, title in [
            (geom_key, geom_ids, 'Geometry'),
            (mat_key, mat_ids, 'Material-SIMP'),
        ]:
            grad_fd = central_difference(controller, fe0, x0_full, key=key, sampled_ids=ids, eps=FD_EPS)
            grad_ad = grad_ad_dict[key][ids]

            abs_err = (grad_ad - grad_fd).abs()
            rel_err = abs_err / (grad_fd.abs() + 1e-12)

            print(f'=== Derivative Check: {title} (Autodiff vs Finite Difference) ===')
            print(f'checked dof: {ids.numel()}')
            print(f'sampled ids: {ids.detach().cpu().tolist()}')
            print(f'fd eps: {FD_EPS:.3e}')
            print(f'min |ad grad| threshold: {MIN_GRAD_ABS:.3e}')
            print(f'max abs err: {abs_err.max().item():.6e}')
            print(f'mean abs err: {abs_err.mean().item():.6e}')
            print(f'max rel err: {rel_err.max().item():.6e}')
            print(f'mean rel err: {rel_err.mean().item():.6e}')
            print('local_idx | full_idx | grad_ad | grad_fd | abs_err | rel_err')
            for i in range(ids.numel()):
                print(
                    f'{i:3d} | '
                    f'{ids[i].item():7d} | '
                    f'{grad_ad[i].item(): .6e} | '
                    f'{grad_fd[i].item(): .6e} | '
                    f'{abs_err[i].item(): .6e} | '
                    f'{rel_err[i].item(): .6e}'
                )
    finally:
        if controller.pools is not None:
            controller.pools.close()
            controller.pools.join()


if __name__ == '__main__':
    main()
