import ctypes
import numpy as np
import torch


from . import sparse as __sparse_methods
import networkx as __nx

def adjust_faces(faces: torch.Tensor, index_remain: torch.Tensor):
    """
    adjust the faces of the mesh
    
    Args:
        faces (torch.Tensor): The faces of the mesh (m x 3).
        index_remain (torch.Tensor): The index of the vertices to remain.
        
    Returns:
        torch.Tensor: The new faces of the mesh (m x 3).
    """
    index_remain = index_remain.unique()
    faces = faces[torch.where(torch.isin(faces, index_remain).sum(
        dim=1) == 3)[0]]

    remain = torch.zeros([faces.max() + 1], dtype=torch.bool)
    remain[index_remain] = True
    cumsum = remain.cumsum(0) - 1
    faces = cumsum[faces]

    return faces


def get_edges(elements: torch.Tensor):
    """
    get the edges of a mesh
    
    Args:
        elements (torch.Tensor): The faces of the mesh (m x 3).
        
    Returns:
        torch.Tensor: The edges of the mesh (n x 2).
    """

    edge0 = torch.stack([elements[:, 0], elements[:, 1]],
                        dim=1).sort(dim=1).values
    edge1 = torch.stack([elements[:, 1], elements[:, 2]],
                        dim=1).sort(dim=1).values
    edge2 = torch.stack([elements[:, 2], elements[:, 0]],
                        dim=1).sort(dim=1).values

    edges = torch.cat([edge0, edge1, edge2], dim=0).unique(dim=0)

    return edges

def get_edges_tet(elements: torch.Tensor):
    """
    get the edges of a mesh
    
    Args:
        elements (torch.Tensor): The faces of the mesh (m x 4).
        
    Returns:
        torch.Tensor: The edges of the mesh (n x 2).
    """

    edge0 = torch.stack([elements[:, 0], elements[:, 1]],
                        dim=1).sort(dim=1).values
    edge1 = torch.stack([elements[:, 0], elements[:, 2]],
                        dim=1).sort(dim=1).values
    edge2 = torch.stack([elements[:, 0], elements[:, 3]],
                        dim=1).sort(dim=1).values
    edge3 = torch.stack([elements[:, 1], elements[:, 2]],
                        dim=1).sort(dim=1).values
    edge4 = torch.stack([elements[:, 1], elements[:, 3]],
                        dim=1).sort(dim=1).values
    edge5 = torch.stack([elements[:, 2], elements[:, 3]],
                        dim=1).sort(dim=1).values

    edges = torch.cat([edge0, edge1, edge2, edge3, edge4, edge5], dim=0).unique(dim=0)

    return edges

# @torch.jit.script
def _get_adjacent_faces(faces: torch.Tensor):
    """
    the edges are sorted in the ascending order
    """

    max_node = faces.max() + 1

    edge1 = faces[:, [1, 2]].sort(dim=1).values
    edge2 = faces[:, [2, 0]].sort(dim=1).values
    edge3 = faces[:, [0, 1]].sort(dim=1).values

    edge1 = edge1[:, 0] * max_node + edge1[:, 1]
    edge2 = edge2[:, 0] * max_node + edge2[:, 1]
    edge3 = edge3[:, 0] * max_node + edge3[:, 1]

    edge_face = torch.stack([edge1, edge2, edge3], dim=1)

    edges00, adjacent_faces0 = edge_face.flatten().sort()
    edges0, num_adjacent_faces = edges00.unique_consecutive(return_counts=True)
    cumsum_adjacent_faces = np.array([0] +
                                     num_adjacent_faces.cumsum(0).tolist())

    index_double_faces = torch.where(num_adjacent_faces == 2)[0].tolist()
    index_single_faces = torch.where(num_adjacent_faces == 1)[0].tolist()
    index_more_faces = torch.where(num_adjacent_faces > 2)[0]
    if index_more_faces.numel() > 0:
        raise Exception('the mesh is not a manifold surface')

    adjacent_faces = torch.ones([edges0.shape[0], 2], dtype=torch.long, device=edges0.device) * -1

    adjacent_faces[
        index_double_faces,
        0] = adjacent_faces0[cumsum_adjacent_faces[index_double_faces]] // 3
    adjacent_faces[index_double_faces, 1] = adjacent_faces0[
        cumsum_adjacent_faces[index_double_faces] + 1] // 3

    adjacent_faces[
        index_single_faces,
        0] = adjacent_faces0[cumsum_adjacent_faces[index_single_faces]] // 3

    edges = torch.zeros([edges0.shape[0], 2],
                        dtype=faces.dtype,
                        device=faces.device)
    edges[:, 0] = edges0 // max_node
    edges[:, 1] = edges0 % max_node

    another_points_index = torch.ones([edges0.shape[0], 2],
                                      dtype=torch.long, device=edges0.device) * -1
    another_points_index[
        index_double_faces,
        0] = adjacent_faces0[cumsum_adjacent_faces[index_double_faces]] % 3
    another_points_index[
        index_double_faces,
        1] = adjacent_faces0[cumsum_adjacent_faces[index_double_faces] + 1] % 3
    # another_points_index = adjacent_faces0.reshape([-1, 2]) % 3

    return edges, adjacent_faces, another_points_index

def get_boundary_edges(elements: torch.Tensor) -> list[torch.Tensor]:
    """
    find the boundary edges of a mesh
    
    Args:
        elements (torch.Tensor): The faces of the mesh (m x 3).
        
    Returns:
        list[torch.Tensor]: The boundary edges of the mesh (n x 2).
    """

    edges, adjacent_faces, another_points_index = _get_adjacent_faces(elements)

    boundary_edges = edges[(adjacent_faces[:, 1] == -1)
                           & (adjacent_faces[:, 0] != -1)]
    boundary_points = torch.unique(boundary_edges.flatten())

    def find_circle(boundary_points):
        boundary_points_circle = boundary_points[0].unsqueeze(0)

        for i in range(boundary_points.shape[0] - 1):
            benow = boundary_edges[(
                boundary_edges == boundary_points_circle[i]).sum(
                    dim=1) > 0].unique()
            ptnow = benow[0]
            if (boundary_points_circle == ptnow).sum() > 0:
                ptnow = benow[1]
                if (boundary_points_circle == ptnow).sum() > 0:
                    ptnow = benow[2]
                    if (boundary_points_circle == ptnow).sum() > 0:
                        break
            boundary_points_circle = torch.cat(
                [boundary_points_circle,
                 ptnow.unsqueeze(0)], dim=0)
        return boundary_points_circle

    result = []
    while boundary_points.shape[0] > 0:
        boundary_points_circle = find_circle(boundary_points)
        boundary_points = torch.tensor(
            list(
                set(boundary_points.tolist()) -
                set(boundary_points_circle.tolist())))
        result.append(boundary_points_circle)
    return result


def edge_length_regularization_2D_part(nodes: torch.Tensor,
                                      elements: torch.Tensor,
                                      index: torch.Tensor,
                                      order=2):
    """
    using the edge length as a spring to regularize the mesh
    
    Args:
        nodes (torch.Tensor): The vertices of the mesh (2 * n).
        elements (torch.Tensor): The faces of the mesh (m x 3).
        index (torch.Tensor): The index of the points to refine.
        
    Returns:
        torch.Tensor: The new vertices of the mesh (2 * n).
    """

    nodes = nodes.detach().clone()
    edges = get_edges(elements)

    while True:
        loss, Ldp, Ldp2 = _closure_edge_length(nodes,
                                               edges,
                                               derivatives=2,
                                               order=order)

        Ldp = Ldp[:, index]
        Ldp2 = Ldp2.index_select(1, index).index_select(3, index)
        Ldp2 = __sparse_methods._sparse_reshape(
            Ldp2, 2 * [2 * Ldp2.shape[1]]).coalesce()

        dP = __sparse_methods._conjugate_gradient(Ldp2.indices(),
                                                  Ldp2.values(),
                                                  -Ldp.flatten(),
                                                  tol=1e-10)
        dP = dP.reshape([2, -1])
        dP.view(-1)[dP.view(-1).isnan()] = 0

        if dP.norm() < 1e-6:
            break

        nodes[:, index] += dP
    
    r1 = nodes[:, elements[:, 0]]
    r2 = nodes[:, elements[:, 1]]
    r3 = nodes[:, elements[:, 2]]
    
    e1 = r2 - r1
    e2 = r3 - r1
    normal = e1[1] * e2[0] - e1[0] * e2[1]
    
    if normal[0] < 0:
        nodes[0] *= -1

    return nodes

def edge_length_regularization_2D(elements: torch.Tensor, weight_boundary = 5.,
                                      order=2):
    """
    using the edge length as a spring to regularize the mesh
    the elements contains all nodes
    
    Args:
        nodes (torch.Tensor): The vertices of the mesh (2 * n).
        elements (torch.Tensor): The faces of the mesh (m x 3).
        index (torch.Tensor): The index of the points to refine.
        
    Returns:
        torch.Tensor: The new vertices of the mesh (2 * n).
    """

    boundary = get_boundary_edges(elements)[0]

    edges_boundary = torch.where(
        torch.isin(get_edges(elements), boundary).sum(dim=1) >= 1)[0]
    
    nodes = torch.randn([2, elements.max() + 1], dtype=torch.float64)
    edges = get_edges(elements)
    
    new_nodes = torch.zeros([2, boundary.shape[0]])
    theta = torch.linspace(0, 2 * np.pi, boundary.shape[0] + 1)[:-1]
    new_nodes[0] = torch.cos(theta)
    new_nodes[1] = torch.sin(theta)
    
    nodes_all = torch.cat([nodes, new_nodes], dim=1)
    edges_all = torch.cat([edges, torch.stack([boundary, torch.arange(nodes.shape[1], nodes.shape[1] + boundary.shape[0])], dim=1)])

    index_remain = torch.ones_like(nodes_all, dtype=torch.bool)

    index_remain[:, nodes.shape[1]:] = False
    index_remain = torch.where(index_remain.flatten())[0]
    
    weight = torch.ones([edges_all.shape[0]], dtype=torch.float64)
    weight[edges.shape[0]:] = weight_boundary
    
    while True:
        # nodes.requires_grad_()
        loss, Ldp, Ldp2 = _closure_edge_length(nodes_all,
                                               edges_all,
                                               weight=weight,
                                               derivatives=2,
                                               order=order)
    
    
        Ldp = Ldp.flatten()[index_remain]
        Ldp2 = __sparse_methods._sparse_reshape(
            Ldp2, 2 * [2 * Ldp2.shape[1]]).index_select(0, index_remain).index_select(1, index_remain).coalesce()

        dP = __sparse_methods._conjugate_gradient(Ldp2.indices(),
                                                  Ldp2.values(),
                                                  -Ldp.flatten(),
                                                  tol=1e-12)

        dP.view(-1)[dP.view(-1).isnan()] = 0

        if dP.norm() < 1e-14:
            break

        nodes_all.view(-1)[index_remain] += dP

    return nodes_all[:, :nodes.shape[1]]

def edge_length_regularization_surf3D(elements: torch.Tensor, 
                                  nodes0: torch.Tensor,
                                  weight_boundary = 1.,
                                      order=2):
    """
    using the edge length as a spring to regularize the mesh
    the elements contains all nodes
    
    Args:
        nodes (torch.Tensor): The vertices of the mesh (2 * n).
        elements (torch.Tensor): The faces of the mesh (m x 3).
        index (torch.Tensor): The index of the points to refine.
        
    Returns:
        torch.Tensor: The new vertices of the mesh (2 * n).
    """
    
    boundary = get_boundary_edges(elements)[0]
    
    index_boundary2 = boundary.clone()
    for i in range(0):
        index_boundary2 = elements[torch.where(
            torch.isin(elements, index_boundary2).sum(
                dim=1) > 0)[0]].unique()

    edges_boundary = torch.where(
        torch.isin(get_edges(elements), index_boundary2).sum(dim=1) >= 1)[0]
    
    nodes = torch.randn([3, elements.max() + 1], dtype=torch.float64) if nodes0 is None else nodes0.clone()
    edges = get_edges(elements)

    index_remain = torch.zeros_like(nodes, dtype=torch.bool)
    index_remain[:, elements.unique()] = True

    index_remain[:, boundary] = False
    index_remain = torch.where(index_remain.flatten())[0]
    
    weight = torch.ones([edges.shape[0]], dtype=torch.float64)
    weight[edges_boundary] = weight_boundary
    while True:
        # nodes.requires_grad_()
        loss, Ldp, Ldp2 = _closure_edge_length(nodes,
                                               edges,
                                               weight=weight,
                                               derivatives=2,
                                               order=order,)
    
    
        Ldp = Ldp.flatten()[index_remain]
        Ldp2 = __sparse_methods._sparse_reshape(
            Ldp2, 2 * [3 * Ldp2.shape[1]]).index_select(0, index_remain).index_select(1, index_remain).coalesce()

        dP = __sparse_methods._conjugate_gradient(Ldp2.indices(),
                                                  Ldp2.values(),
                                                  -Ldp.flatten(),
                                                  tol=1e-10)

        dP.view(-1)[dP.view(-1).isnan()] = 0

        if dP.norm() < 1e-12:
            break
        nodes = nodes.reshape(-1)
        nodes[index_remain] += dP
        nodes = nodes.reshape(3, -1)

    return nodes

def edge_length_regularization_3D(elements: torch.Tensor, 
                                  nodes0: torch.Tensor, 
                                  index: torch.Tensor,
                                  weight_boundary = 1.,
                                      order=2):
    """
    using the edge length as a spring to regularize the mesh
    the elements contains all nodes
    
    Args:
        nodes (torch.Tensor): The vertices of the mesh (2 * n).
        elements (torch.Tensor): The faces of the mesh (m x 3).
        index (torch.Tensor): The index of the points to refine.
        
    Returns:
        torch.Tensor: The new vertices of the mesh (2 * n).
    """
    
    nodes = nodes0.clone()
    edges = get_edges_tet(elements)

    index_remain = torch.zeros_like(nodes, dtype=torch.bool)
    index_remain[:, index] = True

    index_remain = torch.where(index_remain.flatten())[0]

    while True:
        # nodes.requires_grad_()
        loss, Ldp, Ldp2 = _closure_edge_length(nodes,
                                               edges,
                                               derivatives=2,
                                               order=order)
    
    
        Ldp = Ldp.flatten()[index_remain]
        Ldp2 = __sparse_methods._sparse_reshape(
            Ldp2, 2 * [3 * Ldp2.shape[1]]).index_select(0, index_remain).index_select(1, index_remain).coalesce()

        dP = __sparse_methods._conjugate_gradient(Ldp2.indices(),
                                                  Ldp2.values(),
                                                  -Ldp.flatten(),
                                                  tol=1e-10)

        dP.view(-1)[dP.view(-1).isnan()] = 0

        if dP.norm() < 1e-12:
            break
        nodes = nodes.reshape(-1)
        nodes[index_remain] += dP
        nodes = nodes.reshape(3, -1)

    return nodes


def _closure_edge_length(r:torch.Tensor, edges:torch.Tensor, weight:torch.Tensor=None, order=2, derivatives=0):

    if weight is None:
        weight = torch.ones([edges.shape[0]], dtype=r.dtype, device=r.device)
        
    edge_length2 = torch.sum((r[:, edges[:, 0]] - r[:, edges[:, 1]])**2,
                             dim=0).sqrt()
    num_dim = r.shape[0]
    loss = (edge_length2**order*weight).sum()

    if derivatives == 0:
        return [loss]

    Ldl = order * edge_length2**(order - 1)*weight

    ldre = (r[:, edges[:, 0]] - r[:, edges[:, 1]]) / edge_length2
    values_1 = Ldl * ldre

    Ldr = torch.zeros([num_dim, r.shape[1]])
    Ldr.scatter_add_(1, edges[:, 0].unsqueeze(0).repeat(num_dim, 1), values_1)
    Ldr.scatter_add_(1, edges[:, 1].unsqueeze(0).repeat(num_dim, 1), -values_1)

    if derivatives == 1:
        return loss, Ldr

    Ldl_2 = order * (order - 1) * edge_length2**(order - 2)*weight
    ldre_2 = torch.eye(num_dim).reshape(num_dim, num_dim, 1) / edge_length2 + \
            -torch.einsum('ip, jp->ijp', ldre, ldre) / edge_length2

    values_2 = Ldl_2 * torch.einsum('ip,jp->ijp', ldre, ldre) + Ldl * ldre_2
    # diag
    Ldr2_values = [values_2.flatten(), values_2.flatten()]

    # cross item
    Ldr2_values += [-values_2.flatten(), -values_2.flatten()]

    Ldr2_values = torch.cat(Ldr2_values, dim=-1)

    # region : define the indices
    # diag
    Ldr2_indices0 = [
        torch.stack([
            torch.arange(num_dim).reshape([num_dim, 1, 1]).repeat([
                1, num_dim, edges.shape[0]
            ]), edges[:, 0].reshape([1, 1, -1]).repeat([num_dim, num_dim, 1]),
            torch.arange(num_dim).reshape([1, num_dim, 1]).repeat([
                num_dim, 1, edges.shape[0]
            ]), edges[:, 0].reshape([1, 1, -1]).repeat([num_dim, num_dim, 1])
        ],
                    dim=0).reshape([4, -1]),
        torch.stack([
            torch.arange(num_dim).reshape([num_dim, 1, 1]).repeat([
                1, num_dim, edges.shape[0]
            ]), edges[:, 1].reshape([1, 1, -1]).repeat([num_dim, num_dim, 1]),
            torch.arange(num_dim).reshape([1, num_dim, 1]).repeat([
                num_dim, 1, edges.shape[0]
            ]), edges[:, 1].reshape([1, 1, -1]).repeat([num_dim, num_dim, 1])
        ],
                    dim=0).reshape([4, -1]),
    ]

    # cross item
    Ldr2_indices0 += [
        torch.stack([
            torch.arange(num_dim).reshape([num_dim, 1, 1]).repeat(
                [1, num_dim, edges.shape[0]]), edges[:, 0].reshape(
                    [1, 1, edges.shape[0]]).repeat([num_dim, num_dim, 1]),
            torch.arange(num_dim).reshape([1, num_dim, 1]).repeat(
                [num_dim, 1, edges.shape[0]]), edges[:, 1].reshape(
                    [1, 1, edges.shape[0]]).repeat([num_dim, num_dim, 1])
        ],
                    dim=0).reshape([4, -1]),
        torch.stack([
            torch.arange(num_dim).reshape([num_dim, 1, 1]).repeat(
                [1, num_dim, edges.shape[0]]), edges[:, 1].reshape(
                    [1, 1, edges.shape[0]]).repeat([num_dim, num_dim, 1]),
            torch.arange(num_dim).reshape([1, num_dim, 1]).repeat(
                [num_dim, 1, edges.shape[0]]), edges[:, 0].reshape(
                    [1, 1, edges.shape[0]]).repeat([num_dim, num_dim, 1])
        ],
                    dim=0).reshape([4, -1]),
    ]
    Ldr2_indices = torch.cat(Ldr2_indices0, dim=-1)

    # endregion

    Ldr2 = torch.sparse_coo_tensor(Ldr2_indices, Ldr2_values,
                                   [num_dim, r.shape[1], num_dim, r.shape[1]])

    return loss, Ldr, Ldr2


def divide_mesh_by_line(faces: torch.Tensor,
                        circle_line: torch.Tensor,
                        side: int = -1):
    """
    cut the mesh with a line
    
    Args:
        faces (torch.Tensor): The faces of the mesh (m x 3).
        circle_line (torch.Tensor): The line to cut the mesh with the index of the points (n).
        
    Returns:
        tuple[torch.Tensor,torch.Tensor]: The new faces 1 of the mesh (m1 x 3), (m2 x 3).
    """

    delete_index = torch.where(torch.isin(faces, circle_line))[0].unique()

    remain_index = torch.tensor(
        list(set(range(faces.shape[0])) - set(delete_index.tolist())))
    faces_remain = faces[remain_index]

    edges = get_edges(faces_remain)

    if side == -1:
        side = faces_remain[0, 0].item()

    G = __nx.Graph()
    G.add_edges_from(edges.cpu().numpy())
    shortest_path = __nx.single_source_dijkstra(G, side)
    index_part1 = torch.tensor(list(shortest_path[0].keys())).unique()
    index_part2 = torch.tensor(
        list(set(range(faces.max() + 1)) -
             set(index_part1.tolist()))).unique()

    return index_part1, index_part2


def divide_mesh(faces: torch.Tensor):
    """
    divide the mesh into two parts
    
    Args:
        faces (torch.Tensor): The faces of the mesh (m x 3).
        
    Returns:
        tuple[torch.Tensor,torch.Tensor,torch.Tensor]: index of vertices of the first part (n1), index of vertices of the second part (n2), index of the boundary edges (n3).
        
    """
    edges = get_edges(faces)
    G = __nx.Graph()
    G.add_edges_from(edges.cpu().numpy())
    shortest_path = __nx.single_source_dijkstra(G, 50)
    keys = torch.tensor(list(shortest_path[0].keys()))
    values = torch.tensor(list(shortest_path[0].values()))
    mid_values = values[round(len(values) / 2)]

    index_half1 = torch.tensor(keys[values <= mid_values])

    connection1_index = torch.where(
        torch.isin(faces, index_half1).sum(dim=1) == 3)[0]
    connection1 = faces[connection1_index]
    edges = get_edges(faces)

    boundary_points_index = get_boundary_edges(connection1)

    min_diff = 1e10
    for i in range(len(boundary_points_index)):
        index1_1, index1_2 = divide_mesh_by_line(faces,
                                                 boundary_points_index[i])
        diff = abs(index1_1.shape[0] - index1_2.shape[0])
        if diff < min_diff:
            index_half1 = index1_1 if index1_1.shape[0] > index1_2.shape[
                0] else index1_2

    faces_half1 = faces[torch.where(
        torch.isin(faces, index_half1).sum(dim=1) == 3)[0]]
    boundary_index = get_boundary_edges(faces_half1)
    index_half1 = faces_half1.unique()

    index_half1_ = torch.tensor(
        list(set(index_half1.tolist()) - set(boundary_index[0].tolist())))
    index_half2 = torch.tensor(
        list(set(range(faces.max() + 1)) - set(index_half1_.tolist())))

    faces_half2 = faces[torch.where(
        torch.isin(faces, index_half2).sum(dim=1) == 3)[0]]

    index_half2_ = torch.tensor(
        list(set(index_half2.tolist()) - set(boundary_index[0].tolist())))

    return [index_half1_.sort().values,
            faces_half1], [index_half2_.sort().values,
                           faces_half2], boundary_index[0]

def equilateral_triangle_mesh(faces: torch.Tensor) -> torch.Tensor:
    """
    generate a triangular mesh with equilateral triangles
    
    Args:
        vertices (torch.Tensor): The vertices of the mesh (3 * n).
        faces (torch.Tensor): The faces of the mesh (m x 3).
    
    Returns:
        torch.Tensor: The 2D parameterization of the vertices (2 * n).
    """

    unique_index = faces.flatten().unique()

    boundary = get_boundary_edges(faces)[0]

    n = faces.unique().shape[0]
    m = faces.shape[0]
    
    design_variables = torch.randn([2 * unique_index.shape[0] - 4])
    

    index_remain_list = torch.tensor(
        list(set(unique_index.tolist()) - set(boundary[:2].tolist())))
    
    index_remain_list = index_remain_list.sort().values

    def get_uv(design_variables):
        u = torch.zeros([n])
        v = torch.zeros([n])
        u[boundary[0]] = 0
        v[boundary[0]] = 1
        u[boundary[1]] = 0
        v[boundary[1]] = 0
        
        u[index_remain_list] = design_variables.reshape([2, -1])[0]
        v[index_remain_list] = design_variables.reshape([2, -1])[1]
        
        return u, v
    
    def closure(design_variables: torch.Tensor, derivative = 0):
        # design_variables = design_variables.detach().clone().requires_grad_(True)
        u, v = get_uv(design_variables)
        
        uf = u[faces]
        vf = v[faces]
        
        A = (vf[:, 0] - vf[:, 1] + 1/np.sqrt(3) * (2*uf[:, 2] - uf[:, 0] - uf[:, 1]))
        B = (vf[:, 1] - vf[:, 2] + 1/np.sqrt(3) * (2*uf[:, 0] - uf[:, 1] - uf[:, 2]))
        C = (vf[:, 2] - vf[:, 0] + 1/np.sqrt(3) * (2*uf[:, 1] - uf[:, 2] - uf[:, 0]))
        D = (uf[:, 1] - uf[:, 0] + 1/np.sqrt(3) * (2*vf[:, 2] - vf[:, 0] - vf[:, 1]))
        E = (uf[:, 2] - uf[:, 1] + 1/np.sqrt(3) * (2*vf[:, 0] - vf[:, 1] - vf[:, 2]))
        F = (uf[:, 0] - uf[:, 2] + 1/np.sqrt(3) * (2*vf[:, 1] - vf[:, 2] - vf[:, 0]))
        
        loss1 = A**2 + B**2 + C**2 + D**2 + E**2 + F**2 
        
        if derivative==0:
            return loss1.sum()
            
        lduf = torch.zeros_like(uf)
        lduf[:, 0] = \
            2*A * (-1 / np.sqrt(3)) + \
            2*B * (2 / np.sqrt(3)) + \
            2*C * (-1 / np.sqrt(3)) + \
            2*D * (-1) + \
            2*F * (1)
        
        lduf[:, 1] = \
            2 * A * (-1/np.sqrt(3)) +\
            2 * B * (-1/np.sqrt(3)) +\
            2 * C * (2/np.sqrt(3)) +\
            2 * D * (1) +\
            2 * E * (-1)
        lduf[:, 2] = (2 * A * (2/np.sqrt(3)) +
                      2 * B * (-1/np.sqrt(3)) +
                      2 * C * (-1/np.sqrt(3)) +
                      2 * E * (1) +
                      2 * F * (-1))

        ldvf = torch.zeros_like(vf)
        ldvf[:, 0] = (2 * A * (1) +
                      2 * C * (-1) +
                      2 * D * (-1/np.sqrt(3)) +
                      2 * E * (2/np.sqrt(3)) +
                      2 * F * (-1/np.sqrt(3)))
        ldvf[:, 1] = (2 * A * (-1) +
                      2 * B * (1) +
                      2 * D * (-1/np.sqrt(3)) +
                      2 * E * (-1/np.sqrt(3)) +
                      2 * F * (2/np.sqrt(3)))
        ldvf[:, 2] = (2 * B * (-1) +
                      2 * C * (1) +
                      2 * D * (2/np.sqrt(3)) +
                      2 * E * (-1/np.sqrt(3)) +
                      2 * F * (-1/np.sqrt(3)))
        
            

        ldu = torch.zeros_like(u)
        ldv = torch.zeros_like(v)

        ldu.scatter_add_(0, faces.flatten(), lduf.flatten())
        ldv.scatter_add_(0, faces.flatten(), ldvf.flatten())

        lduv = torch.stack([ldu, ldv], dim=0)

        if derivative == 1:
            return loss1.sum(), lduv
        
        lduf_2 = torch.zeros([faces.shape[0], 3, 3], dtype=torch.float64)
        lduf_2[:, 0, 0] = 8
        lduf_2[:, 0, 1] = -4
        lduf_2[:, 0, 2] = -4
        lduf_2[:, 1, 0] = -4
        lduf_2[:, 1, 1] = 8
        lduf_2[:, 1, 2] = -4
        lduf_2[:, 2, 0] = -4
        lduf_2[:, 2, 1] = -4
        lduf_2[:, 2, 2] = 8
        
        
              
        ldufdvf = torch.zeros([faces.shape[0], 3, 3], dtype=torch.float64)
        ldufdvf[:, 0, 1] = 12 / np.sqrt(3)
        ldufdvf[:, 0, 2] = -12 / np.sqrt(3)
        ldufdvf[:, 1, 2] = 12 / np.sqrt(3)
        ldufdvf[:, 1, 0] = -12 / np.sqrt(3)
        ldufdvf[:, 2, 0] = 12 / np.sqrt(3)
        ldufdvf[:, 2, 1] = -12 / np.sqrt(3)
        
        ldvf_2 = torch.zeros([faces.shape[0], 3, 3], dtype=torch.float64)
        ldvf_2[:, 0, 0] = 8
        ldvf_2[:, 0, 1] = -4
        ldvf_2[:, 0, 2] = -4
        ldvf_2[:, 1, 0] = -4
        ldvf_2[:, 1, 1] = 8
        ldvf_2[:, 1, 2] = -4
        ldvf_2[:, 2, 0] = -4
        ldvf_2[:, 2, 1] = -4
        ldvf_2[:, 2, 2] = 8
        
        
        lduv_2_indices1 = torch.stack([
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices2 = torch.stack([
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices3 = torch.stack([
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices4 = torch.stack([
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices = torch.cat([
            lduv_2_indices1.reshape([4, -1]),
            lduv_2_indices2.reshape([4, -1]),
            lduv_2_indices3.reshape([4, -1]),
            lduv_2_indices4.reshape([4, -1])
        ],
                                   dim=1)
        lduv_2_values = torch.cat([
            lduf_2.flatten(),
            ldufdvf.flatten(), -ldufdvf.flatten(),
            ldvf_2.flatten()
        ],
                                  dim=0)

        lduv_2 = torch.sparse_coo_tensor(lduv_2_indices, lduv_2_values,
                                         [2, n, 2, n])

        lduv = lduv[:, index_remain_list].flatten()
        lduv_2 = lduv_2.index_select(1, index_remain_list).index_select(
            3, index_remain_list)
        lduv_2 = __sparse_methods._sparse_reshape(
            lduv_2, 2 * [2 * lduv_2.shape[1]]).coalesce()
        
        
        return loss1.sum(), lduv, lduv_2
    while True:
        

        loss, lduv, lduv_2 = closure(design_variables, derivative=2)
        
        duv = __sparse_methods._conjugate_gradient(lduv_2.indices(),
                                                   lduv_2.values(),
                                                   -lduv.flatten(),
                                                   tol=1e-13)

        print(loss)
        if duv.norm() < 1e-7:
            break

        design_variables += duv
    print(loss)
    return torch.stack(get_uv(design_variables), dim=0)


def LSCM(vertices: torch.Tensor, faces: torch.Tensor):
    """
    Least Squares Conformal Maps (LSCM) parameterization.
    
    Args:
        vertices (torch.Tensor): The vertices of the mesh (3 * n).
        faces (torch.Tensor): The faces of the mesh (m x 3).
    
    Returns:
        torch.Tensor: The 2D parameterization of the vertices (2 * n).
    """

    unique_index = faces.flatten().unique()

    boundary = get_boundary_edges(faces)[0]

    n = vertices.shape[1]
    m = faces.shape[0]
    u = vertices[0].clone()
    v = vertices[1].clone()

    index_remain_list = torch.tensor(
        list(set(unique_index.tolist()) - set(boundary[:2].tolist())))
    # index_remain_list = unique_index[2:]
    # u[boundary[0]] = 0
    # u[boundary[1]] = 1
    # v[boundary[0]] = 0
    # v[boundary[1]] = 0

    # build the local basis for each face
    v0 = vertices[:, faces[:, 0]]
    v1 = vertices[:, faces[:, 1]]
    v2 = vertices[:, faces[:, 2]]
    e1 = v1 - v0
    e2 = v2 - v0
    normal = torch.cross(e1, e2)
    normal = normal / normal.norm(dim=0)
    t1 = e1 / e1.norm(dim=0)
    t2 = torch.cross(normal, t1, dim=0)

    # build the local basis for each vertex
    p0 = torch.zeros([2, m])
    p1 = torch.zeros([2, m])
    p1[0] = (e1 * t1).sum(dim=0)
    p2 = torch.zeros([2, m])
    p2[0] = (e2 * t1).sum(dim=0)
    p2[1] = (e2 * t2).sum(dim=0)

    Area = 0.5 * p1[0] * p2[1] - 0.5 * p1[1] * p2[0]
    M = torch.ones([m, 2, 3])
    M[:, 0, 0] = p1[1] - p2[1]
    M[:, 0, 1] = p2[1] - p0[1]
    M[:, 0, 2] = p0[1] - p1[1]
    M[:, 1, 0] = p2[0] - p1[0]
    M[:, 1, 1] = p0[0] - p2[0]
    M[:, 1, 2] = p1[0] - p0[0]
    M = M / (2 * Area).reshape([-1, 1, 1])

    rotationM = torch.tensor([[0, 1], [-1, 0]], dtype=vertices.dtype).T

    while True:

        uf = u[faces]
        vf = v[faces]

        udot = torch.einsum('fxi,fi->xf', M, uf)
        vdot = torch.einsum('fxi,fi->xf', M, vf)

        loss = (Area *
                (udot - torch.einsum('xf, xy->yf', vdot, rotationM))**2).sum()

        ldudot = 2 * (udot - torch.einsum('xf, xy->yf', vdot, rotationM))
        ldvdot = 2 * (-torch.einsum('xf, yx->yf', udot, rotationM) + vdot)

        lduf = Area.reshape([-1, 1]) * torch.einsum('fxi,xf->fi', M, ldudot)
        ldvf = Area.reshape([-1, 1]) * torch.einsum('fxi,xf->fi', M, ldvdot)

        ldu = torch.zeros_like(u)
        ldv = torch.zeros_like(v)

        ldu.scatter_add_(0, faces.flatten(), lduf.flatten())
        ldv.scatter_add_(0, faces.flatten(), ldvf.flatten())

        lduv = torch.stack([ldu, ldv], dim=0)

        ldudot_2 = 2 * torch.eye(2).reshape(2, 2, 1)
        ldvdot_2 = 2 * torch.eye(2).reshape(2, 2, 1)
        ldudotdvdot = -2 * rotationM.reshape(2, 2, 1)

        lduf_2 = Area.reshape([-1, 1, 1]) * torch.einsum(
            'xyf, fxi, fyj->fij', ldudot_2, M, M)
        ldvf_2 = Area.reshape([-1, 1, 1]) * torch.einsum(
            'xyf, fxi, fyj->fij', ldvdot_2, M, M)
        ldufdvf = -Area.reshape([-1, 1, 1]) * torch.einsum(
            'xyf, fxi, fyj->fij', ldudotdvdot, M, M)

        lduv_2_indices1 = torch.stack([
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices2 = torch.stack([
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices3 = torch.stack([
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices4 = torch.stack([
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices = torch.cat([
            lduv_2_indices1.reshape([4, -1]),
            lduv_2_indices2.reshape([4, -1]),
            lduv_2_indices3.reshape([4, -1]),
            lduv_2_indices4.reshape([4, -1])
        ],
                                   dim=1)
        lduv_2_values = torch.cat([
            lduf_2.flatten(),
            ldufdvf.flatten(), -ldufdvf.flatten(),
            ldvf_2.flatten()
        ],
                                  dim=0)

        lduv_2 = torch.sparse_coo_tensor(lduv_2_indices, lduv_2_values,
                                         [2, n, 2, n])

        lduv = lduv[:, index_remain_list].flatten()
        lduv_2 = lduv_2.index_select(1, index_remain_list).index_select(
            3, index_remain_list)
        lduv_2 = __sparse_methods._sparse_reshape(
            lduv_2, 2 * [2 * lduv_2.shape[1]]).coalesce()

        duv = __sparse_methods._conjugate_gradient(lduv_2.indices(),
                                                   lduv_2.values(),
                                                   -lduv.flatten(),
                                                   tol=1e-13)

        print(loss)
        if duv.norm() < 1e-7:
            break

        duv = duv.reshape([2, -1])

        u[index_remain_list] += duv[0]
        v[index_remain_list] += duv[1]

    return torch.stack([u, v], dim=0)


def LSCM_disk(vertices: torch.Tensor, faces: torch.Tensor):
    """
    Least Squares Conformal Maps (LSCM) parameterization in a disk.
    
    Args:
        vertices (torch.Tensor): The vertices of the mesh (3 * n).
        faces (torch.Tensor): The faces of the mesh (m x 3).
    
    Returns:
        torch.Tensor: The 2D parameterization of the vertices (2 * n).
    """

    unique_index = faces.flatten().unique()

    boundary = get_boundary_edges(faces)[0]

    n = vertices.shape[1]
    m = faces.shape[0]

    index_remain_list = torch.tensor(
        list(set(unique_index.tolist()) - set(boundary.tolist())))
    # index_remain_list = unique_index[2:]

    design_var = torch.randn(
        [2 * index_remain_list.shape[0] + boundary.shape[0]])
    design_var[-boundary.shape[0]:] = torch.linspace(0, 2 * np.pi,
                                                     boundary.shape[0])

    # build the local basis for each face
    v0 = vertices[:, faces[:, 0]]
    v1 = vertices[:, faces[:, 1]]
    v2 = vertices[:, faces[:, 2]]
    e1 = v1 - v0
    e2 = v2 - v0
    normal = torch.cross(e1, e2)
    normal = normal / normal.norm(dim=0)
    t1 = e1 / e1.norm(dim=0)
    t2 = torch.cross(normal, t1, dim=0)

    # build the local basis for each vertex
    p0 = torch.zeros([2, m])
    p1 = torch.zeros([2, m])
    p1[0] = (e1 * t1).sum(dim=0)
    p2 = torch.zeros([2, m])
    p2[0] = (e2 * t1).sum(dim=0)
    p2[1] = (e2 * t2).sum(dim=0)

    Area = 0.5 * p1[0] * p2[1] - 0.5 * p1[1] * p2[0]
    M = torch.ones([m, 2, 3])
    M[:, 0, 0] = p1[1] - p2[1]
    M[:, 0, 1] = p2[1] - p0[1]
    M[:, 0, 2] = p0[1] - p1[1]
    M[:, 1, 0] = p2[0] - p1[0]
    M[:, 1, 1] = p0[0] - p2[0]
    M[:, 1, 2] = p1[0] - p0[0]
    M = M / (2 * Area).reshape([-1, 1, 1])

    rotationM = torch.tensor([[0, 1], [-1, 0]], dtype=vertices.dtype).T

    def closure(design_var):

        var_boundary = design_var[-boundary.shape[0]:]

        u = torch.zeros([n], dtype=vertices.dtype)
        u[index_remain_list] = design_var[:index_remain_list.shape[0]]
        u[boundary] = torch.cos(var_boundary)
        v = torch.zeros([n], dtype=vertices.dtype)
        v[index_remain_list] = design_var[index_remain_list.shape[0]:2 *
                                          index_remain_list.shape[0]]
        v[boundary] = torch.sin(var_boundary)

        uf = u[faces]
        vf = v[faces]

        udot = torch.einsum('fxi,fi->xf', M, uf)
        vdot = torch.einsum('fxi,fi->xf', M, vf)

        loss = (Area * (udot**2 + vdot**2)).sum()

        return loss

    iteration = 0
    while True:
        ind_now = torch.arange(2 * index_remain_list.shape[0] +
                               boundary.shape[0])
        if iteration % 2 == 0:
            ind_now = torch.arange(0, 2 * index_remain_list.shape[0])
        else:
            ind_now = torch.arange(
                2 * index_remain_list.shape[0],
                2 * index_remain_list.shape[0] + boundary.shape[0])

        var_boundary = design_var[-boundary.shape[0]:]

        u = torch.zeros([n], dtype=vertices.dtype)
        u[index_remain_list] = design_var[:index_remain_list.shape[0]]
        u[boundary] = torch.cos(var_boundary)
        v = torch.zeros([n], dtype=vertices.dtype)
        v[index_remain_list] = design_var[index_remain_list.shape[0]:2 *
                                          index_remain_list.shape[0]]
        v[boundary] = torch.sin(var_boundary)

        uf = u[faces]
        vf = v[faces]

        udot = torch.einsum('fxi,fi->xf', M, uf)
        vdot = torch.einsum('fxi,fi->xf', M, vf)

        loss = (Area * (udot**2 + vdot**2)).sum()

        ldudot = 2 * Area * (udot)
        ldvdot = 2 * Area * (vdot)

        lduf = torch.einsum('fxi,xf->fi', M, ldudot)
        ldvf = torch.einsum('fxi,xf->fi', M, ldvdot)

        ldu = torch.zeros_like(u)
        ldv = torch.zeros_like(v)

        ldu.scatter_add_(0, faces.flatten(), lduf.flatten())
        ldv.scatter_add_(0, faces.flatten(), ldvf.flatten())

        uvdboundary = torch.zeros([2, boundary.shape[0]])
        uvdboundary[0] = -torch.sin(var_boundary)
        uvdboundary[1] = torch.cos(var_boundary)

        lduv = torch.stack([ldu, ldv], dim=0)
        ldboundary = torch.einsum('xb, xb->b', lduv[:, boundary], uvdboundary)

        ldudot_2 = 2 * Area * torch.eye(2).reshape(2, 2, 1)
        ldvdot_2 = 2 * Area * torch.eye(2).reshape(2, 2, 1)

        lduf_2 = torch.einsum('xyf, fxi, fyj->fij', ldudot_2, M, M)
        ldvf_2 = torch.einsum('xyf, fxi, fyj->fij', ldvdot_2, M, M)

        lduv_2_indices1 = torch.stack([
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.zeros([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices4 = torch.stack([
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 3, 1]).repeat([1, 1, 3]),
            torch.ones([m, 3, 3], dtype=torch.long),
            faces.reshape([-1, 1, 3]).repeat([1, 3, 1]),
        ])

        lduv_2_indices = torch.cat([
            lduv_2_indices1.reshape([4, -1]),
            lduv_2_indices4.reshape([4, -1])
        ],
                                   dim=1)
        lduv_2_values = torch.cat([lduf_2.flatten(), ldvf_2.flatten()], dim=0)

        lduv_2 = torch.sparse_coo_tensor(lduv_2_indices, lduv_2_values,
                                         [2, n, 2, n]).coalesce()

        uvdboundary_2 = torch.zeros([2, boundary.shape[0]])
        uvdboundary_2[0] = -torch.cos(var_boundary)
        uvdboundary_2[1] = -torch.sin(var_boundary)

        lduvdboundary = (lduv_2.index_select(3, boundary) *
                         uvdboundary).sum(dim=2).coalesce()
        ldboundary_2 = (torch.einsum('xb, xb->b', lduv[:, boundary], uvdboundary_2) * torch.eye(boundary.shape[0]).to_sparse_coo() +\
                (lduvdboundary.index_select(1, boundary) * uvdboundary.unsqueeze(-1)).sum(dim=0)).coalesce()

        ldot = torch.cat([lduv.flatten(), ldboundary], dim=0)

        ldot_2 = torch.zeros(
            [2 * n + boundary.shape[0], 2 * n + boundary.shape[0]])
        ldot_2[:2 * n, :2 * n] = lduv_2.to_dense().reshape(2 * n, 2 * n)
        ldot_2[2 * n:, 2 * n:] = ldboundary_2.to_dense()
        ldot_2[:2 * n, 2 * n:] = lduvdboundary.to_dense().reshape(
            2 * n, boundary.shape[0])
        ldot_2[2 * n:, :2 * n] = lduvdboundary.to_dense().reshape(
            2 * n, boundary.shape[0]).T

        index_remain = torch.cat([
            index_remain_list, index_remain_list + n,
            torch.arange(2 * n, 2 * n + boundary.shape[0])
        ])

        ldot = ldot[index_remain]
        ldot_2 = ldot_2.index_select(0, index_remain).index_select(
            1, index_remain)

        ldot = ldot[ind_now]
        ldot_2 = ldot_2.index_select(0, ind_now).index_select(1, ind_now)

        duv = torch.linalg.solve(ldot_2, -ldot)

        print(loss)

        if iteration % 2 == 1 and duv.norm() < 1e-2:
            break

        if iteration == 1:
            break

        alpha = 1 if (duv * ldot).sum() < 0 else -1
        while True:
            design_var_new = design_var.clone()
            design_var_new[ind_now] += alpha * duv
            loss_new = closure(design_var_new)

            if loss_new < loss:
                break
            else:
                alpha = alpha / 2

            if abs(alpha) < 1e-10:
                break

        design_var[ind_now] += duv * alpha

        iteration += 1

    return torch.stack([u, v], dim=0)

