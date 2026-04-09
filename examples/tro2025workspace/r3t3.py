import os
import sys

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import numpy as np
import torch
import torchfea
import morphopt

def get_surface_volume(assembly: torchfea.Assembly):
    part = assembly.get_part('final_model')
    surfelems = part.surfaces.get_trimesh(name='surface_1_All')
    surfnodes = part.nodes
    p0,p1,p2 = surfnodes[surfelems[:,0]], surfnodes[surfelems[:,1]], surfnodes[surfelems[:,2]]
    normals = torch.cross(p1-p0, p2-p0, dim=1)
    vol = (torch.sum(normals * p0, dim=1).abs() / 6.0).sum()
    # 如果希望体积与 RP 变形相关可用 U1 作为权重
    return vol

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results/', 
                         opt_label='6A3R3T')

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()
            self.jacobian_needed = [f'pressure_{k}' for k in range(1, 7)]

        def objective_function(self):
            assembly = self.fe.assembly
            rp_index = assembly.get_reference_point('RP_head')._RGC_index
            GC_start = assembly._GC_list_indexStart[rp_index]

            total_obj = torch.tensor(0.0, device=assembly.device)

            for i in range(128):
                GC = self.fe_results[i].GC
                jacobian = self.fe_results[i].jacobian

                U_now = GC[GC_start:GC_start+6].clone()

                ratio = ((i // 32) % 2) == 0
                ratio = -1 if ratio else 1

                U1 = U_now.clone() / 3
                U1[3] = (-1 / 36 * U_now[3]**3)
                U1[4] = (-1 / 36 * U_now[4]**3)
                U1[5] = (-1 / 36 * U_now[5]**3)

                Udp_now = torch.cat([jacobian[f'pressure_{k}'][GC_start:GC_start+6, :] for k in range(1, 7)], dim=1)

                if i < 64:
                    Udp_left = Udp_now[1:]
                else:
                    ratio *= -1
                    Udp_left = Udp_now[[4, 5, 0, 1, 2]]

                normal = torch.zeros(6, device=GC.device)
                normal[0] = torch.det(Udp_left[:, 1:])
                normal[1] = torch.det(Udp_left[:, [0, 2, 3, 4, 5]]) * -1
                normal[2] = torch.det(Udp_left[:, [0, 1, 3, 4, 5]])
                normal[3] = torch.det(Udp_left[:, [0, 1, 2, 4, 5]]) * -1
                normal[4] = torch.det(Udp_left[:, [0, 1, 2, 3, 5]])
                normal[5] = torch.det(Udp_left[:, :-1]) * -1
                normal *= ratio

                obj_now = (normal * U1).sum()

                if i == 0:
                    surfobj = get_surface_volume(assembly)
                    obj_now += -surfobj * 0.01

                total_obj = total_obj + obj_now

            return total_obj

        def get_metrics(self):
            return [get_surface_volume(self.fe.assembly).item()]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):
            def __init__(self):
                super().__init__(fea_seed_size=1.4, reinitialize_per_iter=4)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=15., length=100., seed_size=1.0, symmetric=[0], flip=False, maxR=0.1, maxC=0.8, maxFF=0.2))
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.2, flip=True, r0=4., init_location=[8, 0, 30], MaxC=1.2))
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.2, flip=True, r0=4., init_location=[-4, 7, 30], MaxC=1.2))
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.2, flip=True, r0=4., init_location=[-4, -7, 30], MaxC=1.2))
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.2, flip=True, r0=4., init_location=[8, 0, 70], MaxC=1.2))
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.2, flip=True, r0=4., init_location=[-4, 7, 70], MaxC=1.2))
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.2, flip=True, r0=4., init_location=[-4, -7, 70], MaxC=1.2))

            def apply_surface_constraints(self) -> None:
                def _rotate120_240(r0):
                    r0_120 = torch.zeros_like(r0)
                    r0_120[..., 0] = r0[..., 0] * np.cos(2 * np.pi / 3) - r0[..., 1] * np.sin(2 * np.pi / 3)
                    r0_120[..., 1] = r0[..., 0] * np.sin(2 * np.pi / 3) + r0[..., 1] * np.cos(2 * np.pi / 3)
                    r0_120[..., 2] = r0[..., 2]

                    r0_240 = torch.zeros_like(r0)
                    r0_240[..., 0] = r0[..., 0] * np.cos(4 * np.pi / 3) - r0[..., 1] * np.sin(4 * np.pi / 3)
                    r0_240[..., 1] = r0[..., 0] * np.sin(4 * np.pi / 3) + r0[..., 1] * np.cos(4 * np.pi / 3)
                    r0_240[..., 2] = r0[..., 2]
                    return r0_120, r0_240
                    
                surf0 = self.surface_list[0]
                cp0 = surf0._cps.reshape(surf0.model.size[0], surf0.model.size[1], 3)
                num_points = cp0.shape[1] // 3
                r0 = cp0[:, :num_points, :]
                r0_120, r0_240 = _rotate120_240(r0)
                cp0[:, num_points:num_points * 2, :] = r0_120
                cp0[:, num_points * 2:, :] = r0_240
                surf0._cps = cp0.reshape(-1, 3)

                cp1 = self.surface_list[1]._cps.reshape(-1, 3)
                r1_120, r1_240 = _rotate120_240(cp1)
                self.surface_list[2]._cps = r1_120.reshape(-1, 3)
                self.surface_list[3]._cps = r1_240.reshape(-1, 3)

                cp4 = self.surface_list[4]._cps.reshape(-1, 3)
                r4_120, r4_240 = _rotate120_240(cp4)
                self.surface_list[5]._cps = r4_120.reshape(-1, 3)
                self.surface_list[6]._cps = r4_240.reshape(-1, 3)

        class FEAParams(morphopt.FEAParams):
            def define_interface(self):
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 100.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                for k in range(1, 7):
                    self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name=f'surface_{k}_All'), name=f'pressure_{k}')

            def define_steps(self):
                p_max = 0.06
                guassian_points = (np.array([-1 / np.sqrt(3), 1 / np.sqrt(3)]) + 1) / 2 * p_max
                
                pressure = torch.zeros([2, 2, 4, 8, 2, 3])
                pressure[0, 0, :, :, 0, 0] = 0.
                pressure[0, 1, :, :, 0, 0] = p_max
                pressure[1, 0, :, :, 1, 0] = 0.
                pressure[1, 1, :, :, 1, 0] = p_max

                for p1 in range(2):
                    for p2 in range(2):
                        for P1 in range(2):
                            for P2 in range(2):
                                for P3 in range(2):
                                    pressure[0, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 0, 1] = guassian_points[p1]
                                    pressure[0, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 0, 2] = guassian_points[p2]
                                    pressure[0, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 1, 0] = guassian_points[P1]
                                    pressure[0, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 1, 1] = guassian_points[P2]
                                    pressure[0, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 1, 2] = guassian_points[P3]

                                    pressure[1, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 1, 1] = guassian_points[p1]
                                    pressure[1, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 1, 2] = guassian_points[p2]
                                    pressure[1, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 0, 0] = guassian_points[P1]
                                    pressure[1, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 0, 1] = guassian_points[P2]
                                    pressure[1, :, p1 * 2 + p2, P1 * 4 + P2 * 2 + P3, 0, 2] = guassian_points[P3]

                pressure = pressure.reshape([-1, 6]).tolist()
                
                self.set_step_num(128)
                for i in range(128):
                    for k in range(1, 7):
                        self.set_step_params(i, f"pressure_{k}", [pressure[i][k-1]])

        class MaterialParams(morphopt.Materials):
            def __init__(self):
                super().__init__(mu=0.482, kappa=4.8, density=1.08e-9)

        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(morphopt.MorphSolver):
        def __init__(self, params: morphopt.Params):
            super().__init__(params=params, num_process=2)

    class Updater(morphopt.Updaters):
        def __init__(self, params: morphopt.Params, *args, **kwargs):
            super().__init__(surfaces=self.UpdaterSurfaces(params=params), loads=None, *args, **kwargs)

        class UpdaterSurfaces(morphopt.UpdaterGeometries):
            def __init__(self, params: morphopt.Params):
                super().__init__(params=params, max_step_iter=50)
                shape_derivative = self.objectivefuncs.ShapeDerivativeDisplacement()
                self.add_objective_function(shape_derivative)
                self.add_constraints(self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(self.objectivefuncs.Distance(min_distance=np.ones([params.geometry.num_surface, params.geometry.num_surface]) * 2.5))
                self.add_constraints(self.objectivefuncs.boundarys.Cylinder(radius=20., height=97., bottom=3.))


if __name__ == '__main__':
    morphopt.start_optimization(device='cuda:0')
