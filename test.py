import torch

a=torch.randn([3]).requires_grad_()

b=(a**2).sum()

c=b**2
a.requires_grad=False

c.backward()

print(b.grad)
'as '.rstrip()