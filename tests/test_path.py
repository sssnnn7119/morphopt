import os

print(f"Current working directory: {os.getcwd()}")

import torch

print(f"CUDA is available: {torch.cuda.is_available()}")


a = torch.tensor([1.0, 2.0, 3.0], device='cuda:1')

print(f"Tensor on CUDA device: {a}")