import torch


@torch.jit.script
def _conjugate_gradient(A_indices: torch.Tensor,
                        A_values: torch.Tensor,
                        b: torch.Tensor,
                        x0: torch.Tensor = torch.zeros([0]),
                        tol: float = 1e-3,
                        max_iter: int = 1500) -> torch.Tensor:
    dtype0 = A_values.dtype
    A_values = A_values.to(torch.float64)
    b = b.to(torch.float64)
    x0 = x0.to(torch.float64)
    if x0.numel() == 0:
        x0 = torch.zeros_like(b)

    A = torch.sparse_coo_tensor(A_indices, A_values,
                                [b.shape[0], b.shape[0]]).to_sparse_csr()

    r_r0 = torch.dot(b, b)

    x = x0.clone()

    r = b - A @ x
    p = r
    rsold = torch.dot(r, r)

    for i in range(max_iter):
        Ap = A @ p
        alpha = rsold / torch.dot(p, Ap)
        x = x + alpha * p
        r = r - alpha * Ap
        rsnew = torch.dot(r, r)
        if rsnew / r_r0 < tol:
            break
        p = r + rsnew / rsold * p
        rsold = rsnew
        # if i %100 == 0:
        #     print('\riter: %d, residual: %e' % (i, rsnew / r_r0), end='')

    return x.to(A_values.device).to(dtype0)


def _sparse_reshape(sparse_tensor: torch.Tensor, new_shape: list[int]):

    # coalesce the COO sparse tensor
    sparse_tensor = sparse_tensor.coalesce()

    # get the indices and values of the COO sparse tensor
    indices = sparse_tensor._indices()
    values = sparse_tensor._values()

    # get the number of non-zero elements
    nnz = values.numel()

    # get the original shape and new shape of the COO sparse tensor
    original_shape = sparse_tensor.shape

    # get the true index of the COO sparse tensor
    true_indices = torch.zeros([nnz], dtype=torch.long)
    for i in range(len(original_shape)):
        true_indices = true_indices * original_shape[i] + indices[i]

    # calculate the new indices of the COO sparse tensor
    new_indices = torch.zeros([len(new_shape), nnz], dtype=torch.long)
    for i in range(len(new_shape) - 1, -1, -1):
        new_indices[i, :] = true_indices % new_shape[i]
        true_indices = true_indices // new_shape[i]

    # construct the new COO sparse tensor
    new_sparse_tensor = torch.sparse_coo_tensor(new_indices,
                                                values,
                                                size=new_shape)

    return new_sparse_tensor


def _sparse_permute(sparse_tensor: torch.Tensor, permutation):
    sparse_tensor = sparse_tensor.coalesce()
    indices = sparse_tensor.indices()
    values = sparse_tensor.values()
    new_indices = indices[permutation]
    return torch.sparse_coo_tensor(
        new_indices,
        values,
        size=torch.tensor(sparse_tensor.shape)[permutation].tolist())


def _sparse_unsqueeze_repeat(sparse_tensor: torch.Tensor, dim_insert: int,
                             num_repeat: int):
    sparse_tensor = sparse_tensor.coalesce()
    indices = sparse_tensor.indices()
    values = sparse_tensor.values().reshape([-1, 1]).repeat([1, num_repeat
                                                             ]).flatten()
    indices = indices.reshape([indices.shape[0], indices.shape[1],
                               1]).repeat([1, 1, num_repeat])
    indices = torch.cat([
        indices[:dim_insert],
        torch.arange(num_repeat).reshape([1, 1, -1]).repeat(
            [1, indices.shape[1], 1]), indices[dim_insert:]
    ],
                        dim=0).reshape([indices.shape[0] + 1, -1])
    new_size = list(sparse_tensor.shape)
    new_size.insert(dim_insert, num_repeat)
    return torch.sparse_coo_tensor(indices, values, size=new_size)


def _sparse_sum(indices: torch.Tensor,
                values: torch.Tensor,
                dim: int = 1,
                numel_output: int = -1):
    if numel_output == -1:
        numel_output = indices[dim].max().item() + 1
    shape_output = list(values.shape[:-1]) + [numel_output]
    values = values.reshape([-1, values.shape[-1]])
    result = torch.zeros([values.shape[0], numel_output], device=values.device)
    for i in range(values.shape[0]):
        result[i].scatter_add_(0, indices[dim], values[i])
    return result.reshape(shape_output)


def _from_Sdr_to_Sdot_2(indices: torch.Tensor, Sdr_2: torch.Tensor,
                        rdot: torch.Tensor):
    """
    Sdr: [3, num_points, 3, num_points]
    rdot: [num_sparse]
    """
    num_points = Sdr_2.shape[1]
    num_control_points = int(indices[0].max().item() + 1)

    rdot = torch.sparse_coo_tensor(indices=indices.flip(0),
                                   values=rdot,
                                   size=[num_points, num_control_points],
                                   dtype=rdot.dtype,
                                   device=rdot.device).coalesce()

    Sdr_2 = _sparse_reshape(Sdr_2, [3 * 3 * num_points, num_points])
    Sdot = Sdr_2 @ rdot
    Sdot = _sparse_reshape(Sdot, [3, num_points, 3, num_control_points])
    Sdot = _sparse_permute(Sdot, [2, 3, 0, 1])
    Sdot = _sparse_reshape(Sdot, [3 * num_control_points * 3, num_points])
    Sdot = Sdot @ rdot
    Sdot = _sparse_reshape(Sdot,
                           [3, num_control_points, 3, num_control_points])
    return Sdot


def _from_Adr_to_Adot(indices: torch.Tensor,
                      Adr: torch.Tensor = None,
                      Adru: torch.Tensor = None,
                      Adru2: torch.Tensor = None,
                      rdot: torch.Tensor = None,
                      rdudot: torch.Tensor = None,
                      rdu2dot: torch.Tensor = None,
                      numel_output: int = None):
    if Adr is None:
        Adr = torch.zeros([1, 1])
    else:
        Adr = Adr.index_select(-1, indices[1])

    if Adru is None:
        Adru = torch.zeros([1, 1, 1])
    else:
        Adru = Adru.index_select(-1, indices[1])

    if Adru2 is None:
        Adru2 = torch.zeros([1, 1, 1, 1])
    else:
        Adru2 = Adru2.index_select(-1, indices[1])

    if rdot is None:
        rdot = torch.zeros([1])

    if rdudot is None:
        rdudot = torch.zeros([1, 1])

    if rdu2dot is None:
        rdu2dot = torch.zeros([1, 1, 1])

    Adot = torch.einsum('ip, p->ip', Adr, rdot) + \
            torch.einsum('irp, rp->ip', Adru, rdudot) + \
            torch.einsum('irsp, rsp->ip', Adru2, rdu2dot)

    if numel_output is None:
        numel_output = int(indices[0].max().item() + 1)
    Adot = Adot.reshape([-1, int(Adot.shape[-1])])
    result = torch.zeros([int(Adot.shape[0]), numel_output],
                         device=Adot.device)
    for i in range(Adot.shape[0]):
        result[i].scatter_add_(0, indices[0], Adot[i])
    return result
