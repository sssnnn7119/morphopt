import sys
import os

import MorphOpt

import torch

os.environ['CUDA_LAUNCH_BLOCKING'] = '1'

if __name__ == "__main__":
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cuda')
    controller = MorphOpt.restart_optimization(restart_path = "Z:/Results/FRONT_T20251204_133658_ref/", 
                         target_iteration = 18)  
    
    controller.opt_loop()
