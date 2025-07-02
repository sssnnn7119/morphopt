import numpy as np
from mayavi import mlab

def create_simple_density_field(nx=50, ny=50, nz=30):
    """创建一个简单的模拟密度场作为SIMP优化结果"""
    # 创建网格
    x, y, z = np.mgrid[0:nx, 0:ny, 0:nz]
    x = x.astype(float) / nx
    y = y.astype(float) / ny
    z = z.astype(float) / nz
    
    # 设计一个有趣的密度分布模式，模拟SIMP优化的结果
    # 边界条件：左右两侧固定
    left_support = (x < 0.05)
    right_support = (x > 0.95)
    
    # 荷载：中间向下的力
    load_point = ((x > 0.45) & (x < 0.55) & (y > 0.45) & (y < 0.55) & (z > 0.95))
    
    # 创建一些梁状结构
    beam1 = np.abs((y - 0.5) / 0.5) + np.abs((z - 0.5) / 0.5) < 0.2
    beam2 = np.abs((x - 0.5) / 0.5) + np.abs((z - 0.5) / 0.5) < 0.2
    beam3 = ((x - 0.2)**2 + (y - 0.2)**2) < 0.1**2
    beam4 = ((x - 0.8)**2 + (y - 0.8)**2) < 0.1**2
    
    # 创建更多的支撑结构
    distance_from_center = np.sqrt((x - 0.5)**2 + (y - 0.5)**2 + (z - 0.5)**2)
    central_structure = distance_from_center < 0.2
    
    # 组合所有结构，生成密度场
    density = np.zeros((nx, ny, nz))
    density[left_support] += 1.0
    density[right_support] += 1.0
    density[load_point] += 0.8
    density[beam1] += 0.7
    density[beam2] += 0.7
    density[beam3] += 0.9
    density[beam4] += 0.9
    density[central_structure] += 0.5
    
    # 添加一些衰减和噪声，使其看起来更自然
    x_grad = np.sin(x * 5 * np.pi) * 0.1
    y_grad = np.sin(y * 6 * np.pi) * 0.1
    z_grad = np.cos(z * 4 * np.pi) * 0.1
    
    density += x_grad + y_grad + z_grad
    
    # 归一化密度值到 [0.05, 1.0]
    density = np.clip(density, 0, 1.0)
    density = 0.05 + density * 0.95
    
    # 平滑密度场
    from scipy.ndimage import gaussian_filter
    smoothed_density = gaussian_filter(density, sigma=1.0)
    
    return smoothed_density

def visualize_density_with_cutplane(density):
    """使用切平面可视化密度场"""
    # 创建网格
    nx, ny, nz = density.shape
    
    # 创建适当形状的坐标网格 - 确保形状匹配
    x, y, z = np.mgrid[0:nx, 0:ny, 0:nz]
    
    # 创建Mayavi图形窗口
    mlab.figure(bgcolor=(1, 1, 1), size=(900, 800))
    
    # 创建标量场 - 注意：不需要转置，保持一致的形状
    src = mlab.pipeline.scalar_field(x, y, z, density)
    
    # 使用体积渲染
    vol = mlab.pipeline.volume(src, vmin=0.1, vmax=0.8)
      # 设置透明度转换函数
    otf = vol._volume_property.get_scalar_opacity()
    otf.remove_all_points()
    otf.add_point(0.1, 0.0)    # 低密度值透明
    otf.add_point(0.3, 0.1)
    otf.add_point(0.4, 0.3)
    otf.add_point(0.6, 0.7)
    otf.add_point(0.8, 0.9)    # 高密度值不透明
    
    # 设置颜色转换函数 - 适配不同版本的Mayavi
    try:
        # 尝试使用color_transfer_function
        ctf = vol._volume_property.get_color_transfer_function()
    except AttributeError:
        try:
            # 尝试使用color_tf (某些版本使用)
            ctf = vol._volume_property.color_tf
        except AttributeError:
            # 尝试使用gray_transfer_function (根据错误提示)
            ctf = vol._volume_property.get_gray_transfer_function()
    
    # 清除现有点并添加新的颜色点
    ctf.remove_all_points()
    try:
        # 尝试使用add_rgb_point
        ctf.add_rgb_point(0.1, 0.7, 0.7, 0.7)   # 低密度灰色
        ctf.add_rgb_point(0.3, 0.5, 0.5, 0.9)   # 中密度蓝色
        ctf.add_rgb_point(0.7, 0.9, 0.2, 0.3)   # 高密度红色
    except AttributeError:
        # 备用方法，如果add_rgb_point不可用
        ctf.add_point(0.1, 0.7, 0.7, 0.7)   # 低密度灰色
        ctf.add_point(0.3, 0.5, 0.5, 0.9)   # 中密度蓝色
        ctf.add_point(0.7, 0.9, 0.2, 0.3)   # 高密度红色
      # 添加切平面以便更好地查看内部结构
      
      
    # cut_plane = mlab.pipeline.scalar_cut_plane(src,
    #                                            plane_orientation='y_axes',
    #                                            view_controls=True)
    # cut_plane.enable_contours = True
    # cut_plane.contour.number_of_contours = 10
    
    # 添加等值面 - 显示高密度区域
    # contour = mlab.contour3d(x, y, z, density, 
    #                          contours=[0.7], opacity=0.5, 
    #                          color=(1, 0.4, 0.3))
    
    # 添加轮廓和坐标轴
    mlab.outline()
    mlab.axes(xlabel='X', ylabel='Y', zlabel='Z')
    
    # 添加标题
    mlab.title('SIMP 拓扑优化密度场可视化', size=0.4)
    
    # 显示图形
    mlab.show()

if __name__ == "__main__":
    # 创建密度场
    density = create_simple_density_field(60, 40, 20)
    
    # 可视化密度场
    visualize_density_with_cutplane(density)
