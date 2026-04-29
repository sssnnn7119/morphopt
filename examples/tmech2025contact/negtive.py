import os
import sys

os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
import torchfea
import morphopt

ROTATIONPERIOD = 6

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results', 
                         opt_label='JUMP_P6')

    class ObjectiveFunction(morphopt.ObjectiveFunction):


        def objective_function(self):

            rp_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index

            RGC0 = self.fe.assembly._GC2RGC(self.fe_results[0].GC.to(torch.get_default_device()))
            U0 = RGC0[rp_index]
            loss0 = torch.exp((U0[2]+20)/5)/5

            RGC1 = self.fe.assembly._GC2RGC(self.fe_results[1].GC.to(torch.get_default_device()))
            U1 = RGC1[rp_index]
            loss1 = U1[5]

            loss = loss0 + loss1
            return loss

        def get_metrics(self):
            rp_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index
            RGC0 = self.fe.assembly._GC2RGC(self.fe_results[0].GC.to(torch.get_default_device()))
            U0 = RGC0[rp_index]
            loss0 = torch.exp((U0[2]+20)/5)/5
            RGC1 = self.fe.assembly._GC2RGC(self.fe_results[1].GC.to(torch.get_default_device()))
            U1 = RGC1[rp_index]
            return [loss0, U1[5].item()]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):

            def __init__(self):

                super().__init__(fea_seed_size=1.0)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=12.,
                                                            length=50.,
                                                            seed_size=0.8,
                                                            num_U_ratio=ROTATIONPERIOD,
                                                            symmetric=[0, [1]],
                                                            flip=False, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=50/4))
                
                self.add_surface(
                    self.BSP.initialize_cylinder(r0=8.,
                                                        length=44.,
                                                        seed_size=0.8,
                                                        num_U_ratio=ROTATIONPERIOD,
                                                        symmetric=[0, [1]],
                                                        init_location=[0, 0, 3],
                                                        flip=True, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=50/4))

            def _get_all_r(self, rinit: torch.Tensor, flip: bool):
                """
                寮哄埗 U 鏂瑰悜婊¤冻 ROTATIONPERIOD 鐨勬棆杞绉帮紝骞堕澶栦繚璇佸叧浜?xz 骞抽潰鐨勮酱瀵圭О锛?
                U 姝ｅ簭涓庡€掑簭鍒楃殑 x,z 鐩稿悓锛寉 浜掍负鐩稿弽鏁般€?
                鏈熸湜 rinit 褰㈢姸涓?[Nv, Nu, 3]锛孨u 涓?ROTATIONPERIOD 鐨勬暣鏁板€嶃€?
                """
                rout = rinit.clone()

                if rout.dim() != 3 or rout.size(2) < 3:
                    raise ValueError("control_points 闇€瑕佸舰鐘?[Nv, Nu, 3]")

                Nu = rout.shape[1]
                if Nu % ROTATIONPERIOD != 0:
                    raise ValueError(f"U 鏂瑰悜闀垮害 Nu={Nu} 涓嶆槸 ROTATIONPERIOD={ROTATIONPERIOD} 鐨勫€嶆暟")

                # 鏃嬭浆瀵圭О澶嶅埗锛堟寜姣忎釜鍛ㄦ湡鍒?i 涓哄熀鍑嗭級
                for i in range(ROTATIONPERIOD):
                    x0 = rinit[:, i, 0]
                    y0 = rinit[:, i, 1]
                    z0 = rinit[:, i, 2]

                    theta0 = torch.atan2(y0, x0)
                    r0 = torch.sqrt(x0 * x0 + y0 * y0)

                    index_check = torch.arange(i, Nu, ROTATIONPERIOD)
                    theta_all = 2*torch.pi*torch.arange(0, index_check.shape[0])/index_check.shape[0]

                    if flip:
                        theta_all = 2*torch.pi - theta_all

                    x_all = r0.unsqueeze(1) * torch.cos(theta_all.unsqueeze(0) + theta0.unsqueeze(1))
                    y_all = r0.unsqueeze(1) * torch.sin(theta_all.unsqueeze(0) + theta0.unsqueeze(1))
                    z_all = z0.unsqueeze(1).repeat(1, len(index_check))
                    rout[:, index_check] = torch.stack([x_all, y_all, z_all], dim=-1)

                # 杞村绉帮紙鍏充簬 xz 骞抽潰锛夛細U 姝ｅ簭涓庡€掑簭涓€鑷达紝y 涓虹浉鍙嶆暟
                # 灏嗗悗鍗婃闀滃儚涓哄墠鍗婃锛屼繚鎸佽嚜娲?
                rout[:, :, 0] = (rout[:, :, 0] + rout[:, :, 0].flip(dims=[1])) / 2
                rout[:, :, 2] = (rout[:, :, 2] + rout[:, :, 2].flip(dims=[1])) / 2
                rout[:, :, 1] = (rout[:, :, 1] - rout[:, :, 1].flip(dims=[1])) / 2

                # 杞村绉?锛堝叧浜巣=25骞抽潰锛?
                rout[:, :, 0] = (rout[:, :, 0] + rout[:, :, 0].flip(dims=[0])) / 2
                rout[:, :, 1] = (rout[:, :, 1] + rout[:, :, 1].flip(dims=[0])) / 2
                rout[:, :, 2] = (rout[:, :, 2] - (rout[:, :, 2].flip(dims=[0]) - 50)) / 2

                return rout
            
            def apply_surface_constraints(self):
                cp0 = self.surface_list[0].control_points
                surfinterface0: morphopt.GeometryParams.BSP = self.surface_list[0]
                cp0 = cp0.reshape(surfinterface0.model.size[0], surfinterface0.model.size[1], 3)
                surfinterface0._cps = self._get_all_r(cp0, self.surface_list[0].flip).reshape(-1, 3)

                cp1 = self.surface_list[1].control_points
                surfinterface1: morphopt.GeometryParams.BSP = self.surface_list[1]
                cp1 = cp1.reshape(surfinterface1.model.size[0], surfinterface1.model.size[1], 3)
                surfinterface1._cps = self._get_all_r(cp1, self.surface_list[1].flip).reshape(-1, 3)

        class FEAParams(morphopt.FEAParams):

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
                self.set_step_params(1, "moment_1", [0.0, 0.0, 100.0])


        class MaterialParams(morphopt.Materials):
            
            def __init__(self):
                super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())


    class Solver(morphopt.MorphSolver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.Params):

            super().__init__(params=params,
                            task_index_list=[[0, 1]],
                            num_process=1)

    class Updater(morphopt.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: morphopt.Params, *args, **kwargs):
            super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                            loads=None, *args, **kwargs)

        class UpdaterSurfaces(morphopt.UpdaterGeometries):
            """
            Updater class for morphopt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self, params: morphopt.Params):

                super().__init__(
                    params=params,
                    max_step_iter=50, max_step_length=0.4)

                shape_derivative = self.objectivefuncs.ShapeDerivative()
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
    morphopt.start_optimization(device='cuda:0')

