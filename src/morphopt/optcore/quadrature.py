"""Boundary quadrature for workspace integrals in actuation space."""

from itertools import product

import numpy as np


def actuation_boundary_gauss_points(bounds, order):
    """Return Gauss points, weights, oriented tangents, and signs on a box boundary.

    ``bounds`` contains one finite ``(lower, upper)`` pair per actuation input.
    Two-dimensional domains return their four oriented edges; three-dimensional
    domains return their six outward-oriented faces. ``order`` Gauss points are
    used along every free coordinate of each edge or face.

    The tangent array has shape ``(n_points, 2)``. For a 2-D domain its second
    column is ``-1``; for a 3-D domain both columns identify the face tangents.
    Weights are scaled to the physical actuation bounds.
    """
    bounds = np.asarray(bounds, dtype=float)
    if (
        bounds.ndim != 2
        or bounds.shape[1] != 2
        or bounds.shape[0] not in (2, 3)
        or not np.isfinite(bounds).all()
        or (bounds[:, 1] <= bounds[:, 0]).any()
    ):
        raise ValueError("Actuation bounds must define a finite 2-D or 3-D box.")
    if not isinstance(order, int) or order < 1:
        raise ValueError("Gaussian order must be a positive integer.")

    dimension = len(bounds)
    nodes, weights_1d = np.polynomial.legendre.leggauss(order)
    half = (bounds[:, 1] - bounds[:, 0]) / 2
    center = bounds.mean(axis=1)
    points, weights, tangents, orientations = [], [], [], []

    if dimension == 2:
        # Counter-clockwise edge orientation in the actuation plane.
        edge_data = (
            (0, 0, 1, -1),
            (0, 1, 1, 1),
            (1, 0, 0, 1),
            (1, 1, 0, -1),
        )
        for fixed_axis, side, tangent_axis, orientation in edge_data:
            for index, node in enumerate(nodes):
                point = center.copy()
                point[tangent_axis] = center[tangent_axis] + half[tangent_axis] * node
                point[fixed_axis] = bounds[fixed_axis, side]
                points.append(point)
                weights.append(half[tangent_axis] * weights_1d[index])
                tangents.append((tangent_axis, -1))
                orientations.append(orientation)
    else:
        # Tangent pairs satisfy e_a × e_b = the positive coordinate normal.
        face_tangents = ((1, 2), (2, 0), (0, 1))
        for fixed_axis, (tangent_a, tangent_b) in enumerate(face_tangents):
            for side, orientation in ((0, -1), (1, 1)):
                for indices in product(range(order), repeat=2):
                    point = center.copy()
                    point[fixed_axis] = bounds[fixed_axis, side]
                    point[tangent_a] += half[tangent_a] * nodes[indices[0]]
                    point[tangent_b] += half[tangent_b] * nodes[indices[1]]
                    points.append(point)
                    weights.append(
                        half[tangent_a] * half[tangent_b]
                        * weights_1d[indices[0]] * weights_1d[indices[1]]
                    )
                    tangents.append((tangent_a, tangent_b))
                    orientations.append(orientation)

    return (
        np.asarray(points),
        np.asarray(weights),
        np.asarray(tangents, dtype=int),
        np.asarray(orientations, dtype=float),
    )
