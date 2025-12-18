import os
import sys

import FEA
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
import MorphOpt

ROTATIONPERIOD = 6

class ThisController(MorphOpt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results', 
                         opt_label='JUMP')

    class ObjectiveFunction(MorphOpt.ObjectiveFunction):
        def get_objective(self, *args, **kwargs):
            
            device0 = torch.tensor(1).device

            rp_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index
            RGC0 = self.fe.assembly._GC2RGC(self.U[0].to(device0))
            U0 = RGC0[rp_index]

            RGC1 = self.fe.assembly._GC2RGC(self.U[1].to(device0))
            U1 = RGC1[rp_index]

            loss0 = torch.exp((U0[2]+20)/5)/5
            loss1 = U1[5] * 0

            return loss0 + loss1

    class Params(MorphOpt.Params):
        class GeometryParams(MorphOpt.GeometryParams):

            def __init__(self):

                super().__init__(fea_seed_size=1.5, fea_mesh_order=1)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=12.,
                                                            length=50.,
                                                            seed_size=0.8,
                                                            num_U_ratio=ROTATIONPERIOD,
                                                            symmetric=[0, [1]],
                                                            flip=False, maxR=0.1, maxC=1.5, maxFF=0.2, perturbation_L=50/4))
                
                self.add_surface(
                    self.BSP.initialize_cylinder(r0=8.,
                                                        length=44.,
                                                        seed_size=0.8,
                                                        num_U_ratio=ROTATIONPERIOD,
                                                        symmetric=[0, [1]],
                                                        init_location=[0, 0, 3],
                                                        flip=True, maxR=0.1, maxC=1.5, maxFF=0.2, perturbation_L=50/4))

            # def _get_all_r(self, rinit: torch.Tensor):
            #     rout = rinit.clone()
            #     num_points = rinit.shape[2] / 4
            #     num_points = int(num_points)
            #     r0 = rinit[:, :, :num_points]
            #     r1 = r0.clone()
            #     r1[0] *= -1
            #     rout[:, :, num_points:num_points*2] = r1.flip(dims=[2])
            #     r2 = r0.clone()
            #     r2[0] *= -1
            #     r2[1] *= -1
            #     rout[:, :, num_points*2:num_points*3] = r2
            #     r3 = r0.clone()
            #     r3[1] *= -1
            #     rout[:, :, num_points*3:num_points*4] = r3.flip(dims=[2])
            #     return rout

            def _get_all_r(self, rinit: torch.Tensor, flip: bool):
                """
                强制 U 方向满足 ROTATIONPERIOD 的旋转对称，并额外保证关于 xz 平面的轴对称：
                U 正序与倒序列的 x,z 相同，y 互为相反数。
                期望 rinit 形状为 [3, Nv, Nu]，Nu 为 ROTATIONPERIOD 的整数倍。
                """
                rout = rinit.clone()

                if rout.dim() != 3 or rout.size(0) < 3:
                    raise ValueError("control_points 需要形状 [3, Nv, Nu]")

                Nu = rout.shape[2]
                if Nu % ROTATIONPERIOD != 0:
                    raise ValueError(f"U 方向长度 Nu={Nu} 不是 ROTATIONPERIOD={ROTATIONPERIOD} 的倍数")

                # 旋转对称复制（按每个周期列 i 为基准）
                for i in range(ROTATIONPERIOD):
                    x0 = rinit[0, :, i]
                    y0 = rinit[1, :, i]
                    z0 = rinit[2, :, i]

                    theta0 = torch.atan2(y0, x0)
                    r0 = torch.sqrt(x0 * x0 + y0 * y0)

                    index_check = torch.arange(i, Nu, ROTATIONPERIOD)
                    theta_all = 2*torch.pi*torch.arange(0, index_check.shape[0])/index_check.shape[0]

                    if flip:
                        theta_all = 2*torch.pi - theta_all

                    x_all = r0.unsqueeze(1) * torch.cos(theta_all.unsqueeze(0) + theta0.unsqueeze(1))
                    y_all = r0.unsqueeze(1) * torch.sin(theta_all.unsqueeze(0) + theta0.unsqueeze(1))
                    z_all = z0.unsqueeze(1).repeat(1, len(index_check))
                    rout[0, :, index_check] = x_all
                    rout[1, :, index_check] = y_all
                    rout[2, :, index_check] = z_all

                # 轴对称（关于 xz 平面）：U 正序与倒序一致，y 为相反数
                # 将后半段镜像为前半段，保持自洽
                rout[0] = (rout[0] + rout[0].flip(dims=[1])) / 2
                rout[2] = (rout[2] + rout[2].flip(dims=[1])) / 2
                rout[1] = (rout[1] - rout[1].flip(dims=[1])) / 2

                # 轴对称 （关于z=25平面）
                rout[0] = (rout[0] + rout[0].flip(dims=[0])) / 2
                rout[1] = (rout[1] + rout[1].flip(dims=[0])) / 2
                rout[2] = (rout[2] - (rout[2].flip(dims=[0]) - 50)) / 2

                return rout
            
            def apply_surface_constraints(self):
                self.surface_list[0].control_points = self._get_all_r(self.surface_list[0].control_points, self.surface_list[0].flip)
                self.surface_list[1].control_points = self._get_all_r(self.surface_list[1].control_points, self.surface_list[1].flip)

        class FEAParams(MorphOpt.FEAParams):

            def __init__(self):
                super().__init__()

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 50.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'),
                                        name='pressure_1')
                self.add_fea_interface(self.ConcentratedMomentInterface(rp_name='RP_head'),
                                    name='moment_1')
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_0_All',),
                                        name='contact_0')
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_1_All',),
                                        name='contact_1') 
                

            def define_steps(self):
                self.set_step_num(2)

                self.set_step_params(0, "pressure_1", [-0.05])
                self.set_step_params(0, "moment_1", [0.0, 0.0, 0.0])

                self.set_step_params(1, "pressure_1", [-0.05])
                self.set_step_params(1, "moment_1", [0.0, 0.0, 0.0])


        class MaterialParams(MorphOpt.Materials):
            
            def __init__(self):
                super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())


    class Solver(MorphOpt.MorphSolver):
        """
        Solver class for MorphOpt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: MorphOpt.Params):

            super().__init__(params=params,
                            task_index_list=[[0, 1]],
                            num_process=1)

    class Updater(MorphOpt.Updaters):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: MorphOpt.Params, *args, **kwargs):
            super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                            loads=None, *args, **kwargs)

        class UpdaterSurfaces(MorphOpt.UpdaterSurfaces):
            """
            Updater class for MorphOpt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self, params: MorphOpt.Params):

                super().__init__(
                    params=params,
                    max_step_iter=50, max_step_length=0.4)

                shape_derivative = self.objectivefuncs.ShapeDerivativeDisplacement()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[1.0, 2.5],
                                                                [2.5, 2.0]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=15., height=50., bottom=0.))

    
if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')

    controller = ThisController()
    controller.start_optimization()
