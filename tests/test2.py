
import os
import sys

from sympy import im

sys.path.append(os.getcwd())
import FEA
import CPGEO
import Bspline

import mayavi
from mayavi import mlab
import numpy as np
# 创建立方体的网格数据
x, y, z = np.mgrid[-1:1:20j, -1:1:20j, -1:1:20j]

# 定义标量场和透明度场
scalars = np.sqrt(x**2 + y**2 + z**2)
alpha = scalars

# 将 alpha 作为标量场的第四个分量（RGBA）
field = mlab.pipeline.scalar_field(x, y, z, scalars)
field.image_data.point_data.add_array(alpha.ravel())
field.image_data.point_data.get_array(1).name = 'alpha'
field.update()

# 绘制体积渲染
vol = mlab.pipeline.volume(field)

contour = mlab.contour3d(x, y, z, scalars, 
                            contours=[0.7], opacity=0.5, 
                            color=(1, 0.4, 0.3))


# 添加轮廓线和坐标轴以便更好地可视化
mlab.outline()
mlab.axes()
mlab.show()