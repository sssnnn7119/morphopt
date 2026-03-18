

from torchfea import inp

import morphopt
import torch
import importlib.util
torch.set_default_dtype(torch.float64)
torch.set_default_device('cuda')


def readhistoryparams(path_result: str, iteration: int = -1) -> morphopt.Params:
    spec = importlib.util.spec_from_file_location("MAIN_SCRIPT_FOR_RESTART", path_result + '/scripts/' + 'MAIN_SCRIPT_FOR_RESTART.py')
    MAIN_SCRIPT_FOR_RESTART = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MAIN_SCRIPT_FOR_RESTART)


    Controller: morphopt.Controller = MAIN_SCRIPT_FOR_RESTART.ThisController

    controller: morphopt.Controller = Controller()

    controller._load_history(path_result=path_result, target_iteration=iteration)


    return controller

if __name__ == "__main__":


    path_result = 'A:/MineData/Learning/Publications/TMECH2025Contact/results/Optimization/grasp/result/GRASP_T20260302_163335'
    
    controller: morphopt.Controller = readhistoryparams(path_result, 294)

    inp = controller.params.geometry.generate()
    fe = controller.params.feamodel.create_fea(inp=inp)
    controller.params.materials.set_materials(fe)
    fe.initialize()

    controller.params.feamodel.process_fea(fe, 0)

    totaliter = 21
    mesh = fe.assembly.get_instance('final_model').get_mesh(surf_name='surface_0_All')
    exmesh = fe.assembly.get_instance('cylinder').get_mesh(surf_name='contact')
    exmesh.save('Z:/temp/contact_cylinder.obj')
    for i in range(totaliter):
        print('Iteration %d / %d' % (i + 1, totaliter))
        pressure_now = 0.08 * (i) / (totaliter-1)
        print('Pressure: %.4f' % pressure_now)
        fe.assembly.get_load('P_s1').pressure = pressure_now
        result = fe.solve()
        RGCcylinder = fe.assembly.RGC[fe.assembly.get_instance('cylinder')._RGC_index]
        RGCmodel = fe.assembly.RGC[fe.assembly.get_instance('final_model')._RGC_index]

        mesh.points = RGCmodel.cpu().numpy() + fe.assembly.get_instance('final_model').nodes.cpu().numpy()
        mesh.save('Z:/temp/model_%d.obj' % i)
    

    raise Exception("For Debugging Only")