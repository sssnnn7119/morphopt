
from ..optcore.controller import Controller as ThisController
import torch
import torchfea
import copy

def _run_once(
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
    return controller.objfun.compute_multistep_objective(fe_results=controller.objfun.fe_results, assembly=fe.assembly)


def _central_difference(
    controller: ThisController,
    fe_template: torchfea.FEAController,
    x0_full: dict[str, torch.Tensor],
    key: str,
    sampled_ids: torch.Tensor,
    eps: float = 1e-2,
) -> torch.Tensor:
    grad_fd = torch.zeros(sampled_ids.numel(), dtype=x0_full[key].dtype, device=x0_full[key].device)
    for i, idx in enumerate(sampled_ids):
        xp_dict = {k: v.clone() for k, v in x0_full.items()}
        xm_dict = {k: v.clone() for k, v in x0_full.items()}
        xp_dict[key][idx] += eps
        xm_dict[key][idx] -= eps

        fp = _run_once(controller, fe_template, xp_dict)
        fm = _run_once(controller, fe_template, xm_dict)
        grad_fd[i] = (fp - fm) / (2.0 * eps)
    return grad_fd

def _sample_ids_by_gradient(
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

def check_gradients(controller: ThisController, N_GEOM_CHECK: int = 10, N_MAT_CHECK: int = 10, MIN_GRAD_ABS: float = 1e-6, FD_EPS: float = 1e-2):
    import morphopt
    import tempfile

    morphopt.controller = controller
    controller.initialize()

    try:
        with tempfile.TemporaryDirectory(prefix='cache_derivative_check_') as cache_dir:
            fe0 = controller.params.create_feamodel(path_result=cache_dir + '/', pools=controller.pools)
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

        geom_ids = _sample_ids_by_gradient(
            grad_full=grad_ad_dict[geom_key],
            count=N_GEOM_CHECK,
            min_abs=MIN_GRAD_ABS,
        )
        mat_ids = _sample_ids_by_gradient(
            grad_full=grad_ad_dict[mat_key],
            count=N_MAT_CHECK,
            min_abs=MIN_GRAD_ABS,
        )

        for key, ids, title in [
            (geom_key, geom_ids, 'Geometry'),
            (mat_key, mat_ids, 'Material-SIMP'),
        ]:
            if ids.numel() == 0:
                print(f'No {title} gradient exceeds the minimum threshold of {MIN_GRAD_ABS:.3e}. Skipping derivative check.')
                continue
            grad_fd = _central_difference(controller, fe0, x0_full, key=key, sampled_ids=ids, eps=FD_EPS)
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

