import ctypes

import torch
import numpy as np
import os
filepath = os.path.dirname(os.path.abspath(__file__))
face_api = ctypes.CDLL(os.path.join(filepath, 'MorphOptCore.dll'))


def get_distance_penalty(points: torch.Tensor, normal: torch.Tensor, surface_index, distance_threshold: float) -> torch.Tensor:
    """
    Calculate the distance penalty for a set of points and their normals.

    Args:
        points (torch.Tensor): Tensor of shape (N, 3) representing the points.
        normal (torch.Tensor): Tensor of shape (N, 3) representing the normals at the points.
        surface_index (torch.Tensor): Tensor of shape (N,) representing the index of the surface each point belongs to.
        distance_threshold (float): The distance threshold for the penalty.

    Returns:
        pair_points (torch.Tensor): Tensor of shape (M, 2) containing pairs of indices of points that are within the distance threshold.
    """
    # Get number of points
    num_points = points.shape[0]
    
    # Convert torch tensors to numpy arrays
    points_np = points.cpu().contiguous().numpy()
    normal_np = normal.cpu().contiguous().numpy()
    
    # Get C-contiguous arrays and pointers
    points_flat = np.ascontiguousarray(points_np.reshape(-1), dtype=np.float64)
    normal_flat = np.ascontiguousarray(normal_np.reshape(-1), dtype=np.float64)
    surface_index_flat = np.ascontiguousarray(surface_index.cpu().numpy(), dtype=np.int32)
    
    points_ptr = points_flat.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    normal_ptr = normal_flat.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    surface_index_ptr = surface_index_flat.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    
    # Set up function signatures
    face_api.CalculatePointPairs.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double), 
                                           ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int)
                                           , ctypes.c_double]
    face_api.CalculatePointPairs.restype = ctypes.c_int
    
    # Call the function
    num_pairs = face_api.CalculatePointPairs(num_points, points_ptr, normal_ptr, surface_index_ptr, ctypes.c_double(distance_threshold))
    
    # If no pairs found, return empty tensor
    if num_pairs == 0:
        return torch.zeros((0, 3), dtype=torch.int64)
    
    # Allocate numpy array for results
    result_np = np.zeros(num_pairs * 2, dtype=np.int32)
    result_ptr = result_np.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    
    # Set up GetPointPairs function
    face_api.GetPointPairs.argtypes = [ctypes.POINTER(ctypes.c_int)]
    face_api.GetPointPairs.restype = ctypes.c_bool
    
    # Get the point pairs
    success = face_api.GetPointPairs(result_ptr)
    if not success:
        return torch.zeros((0, 3), dtype=torch.int64)
    
    # Reshape and convert back to torch tensor
    result_tensor = torch.from_numpy(result_np.reshape(num_pairs, 2)).to(torch.int64).to(points.device)

    return result_tensor

