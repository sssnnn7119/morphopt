import torch

a=torch.randn([40000,40000])

print(a)

del a

import gc
gc.collect()

print("done")

torch.cuda.empty_cache()

print("done2")