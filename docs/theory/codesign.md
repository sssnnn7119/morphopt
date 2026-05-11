# 气腔-外骨骼材料协同优化（Co-Design）

> 本文档阐述 MorphOpt 框架中气动软体机器人的气腔形状与外部骨架材料的**协同优化方法**。该方法在变形形态优化（TRO2023Morph）的基础上，引入基于 SIMP 的材料拓扑优化，并结合偏置壳单元技术实现薄壁气腔的高效仿真，形成一套完整的气-固耦合协同设计流程。

---

## 目录

1. [问题概述](#1-问题概述)
2. [几何建模：偏置壳单元](#2-几何建模偏置壳单元)
3. [外骨骼材料设计：SIMP 拓扑优化](#3-外骨骼材料设计simp-拓扑优化)
4. [Fscrw 正则化方法](#4-fscrw-正则化方法)
5. [形状-材料联合优化模型](#5-形状-材料联合优化模型)
6. [协同约束](#6-协同约束)
7. [灵敏度分析与自动微分](#7-灵敏度分析与自动微分)
8. [数值流程](#8-数值流程)
9. [完整代码示例](#9-完整代码示例)
10. [参考文献](#10-参考文献)

---

## 1. 问题概述

### 1.1 设计背景

气动软体机器人的变形由**两个关键因素**共同决定：

1. **气腔形态**：内部空腔的几何形状决定了气压驱动的方向与分布
2. **外骨架材料分布**：外部/SIMP 材料的刚度分布决定了变形的约束与放大

传统方法通常仅优化气腔几何，而假定外壁材料均匀。MorphOpt 的 **codesign 子模块** 将二者统一优化，在允许气腔形状自由演进的同时，通过 SIMP 方法自动设计外壁材料的空间分布，从而获得更优的变形性能。

### 1.2 核心创新

| 创新点 | 描述 | 代码位置 |
|-------|------|---------|
| **偏置壳单元** | 基于球面映射气腔 + 法向偏置生成楔形单元(C3D6)，精确仿真薄壁气腔变形 | `codesign/geometry.py: _build_shell_c3d6()` |
| **SIMP 外骨架** | B 样条场参数化材料密度，拓扑优化骨架分布 | `codesign/material.py: CodesignMaterials` |
| **Fscrw 正则化** | 惩罚位移二阶梯度的反对称分量，抑制 SIMP 低密度区的零能模式 | `simpmaterial.py: SIMPElementFsrew` |
| **协同约束** | 内凹曲率约束 + 偏移面最小距离，确保壳结构可制造性 | `codesign/constraints.py` |

### 1.3 问题形式化

设计目标：最小化系统在某载荷下的**总势能**（即最大化结构刚度），同时优化气腔形态和材料分布：

$$
\min_{\mathbf{\Phi}_G, \mathbf{\Phi}_M} \mathcal{J} = \Pi_{\text{总}}(\mathbf{u}, \mathbf{\Phi}_G, \mathbf{\Phi}_M)
$$

其中：
- $\mathbf{\Phi}_G$ 为气腔几何控制点（球面映射 CPGEO）
- $\mathbf{\Phi}_M$ 为材料密度场控制点（SIMP B 样条场）
- $\Pi_{\text{总}}$ 为系统总势能，可包含多个载荷工况的加权和

平衡约束：

$$
\mathbf{R}(\mathbf{u}, \mathbf{\Phi}_G, \mathbf{\Phi}_M) = 0
$$

即位移场 $\mathbf{u}$ 由气腔几何和材料分布共同决定。

---

## 2. 几何建模：偏置壳单元

### 2.1 整体思路

气腔采用球面映射闭曲面（CPGEO）描述，外部实体由气腔表面沿法向偏置生成薄壁实体。为提高薄壁结构的仿真精度和计算效率，采用**楔形单元（C3D6）**层叠的方式构建偏置壳网格。

```
完整的有限元模型 = 
  外部 C3D4 网格     → SIMP 材料（拓扑优化区域）
+ 气腔壁 C3D6 网格   → 均匀软材料（气腔偏置层）
```

![](figs/codesign_mesh_concept.png) <!-- 概念图 -->

### 2.2 壳单元构建流程

`CodesignGeometry._build_shell_c3d6()` 实现了完整的壳构建流程：

```
算法：偏置壳网格生成
———————————————————————————————————
输入：基础四面体网格 part，壳厚度 thickness，层数 num_layers
1. 获取气腔表面三角形网格 (surface_1_All, surface_2_All, ...)
2. 将表面节点映射为基底层（layer 0）
3. 对每一层 layer = 1..num_layers:
   α = layer / num_layers
   新节点 = 基节点 + α × 厚度 × 法向量
4. 连接相邻层节点，构建 C3D6 楔形单元
5. 在最外层创建偏移表面 (surface_1_offset, ...)，用于施加气压载荷
6. 返回更新后的 part
———————————————————————————————————
```

核心代码：

```python
# src/morphopt/codesign/geometry.py

def _build_shell_c3d6(self, part: torchfea.Part) -> torchfea.Part:
    # 获取气腔表面三角网格
    tri_by_surface = {}
    for sidx in range(1, int(self.num_surface)):
        surf_name = f"surface_{sidx}_All"
        tri = part.surfaces.get_trimesh(surf_name)
        tri_by_surface[sidx] = tri

    # 对每一层，沿法向偏移生成节点
    for layer in range(1, self.num_layers + 1):
        alpha = float(layer) / float(self.num_layers)
        new_xyz = base_nodes + alpha * disp
        nodes_all = torch.cat([nodes_all, new_xyz], dim=0)

    # 构建 C3D6 楔形单元连接
    wedge6 = np.stack([n0, n1, n2, n3, n4, n5], axis=1)
    part.add_element(element, name="C3D6")

    # 创建偏移表面（用于气压加载）
    part.add_surface_set(surf_name_offset, [(elem_ids, 1)])
```

### 2.3 法向量计算

精确的法向量对于偏置壳的质量至关重要。`CodesignGeometry` 通过两种方式计算法向量：

1. **基于 CPGEO 曲面的解析法向量**（用于敏感度分析）：

```python
def _compute_normals(self, base_nodes, tri_local):
    normal_list = []
    for sfidx in range(1, self.num_surface):
        normals = self.surface_list[sfidx].get_normals(surf_node_uv)
        normal_list.append(normals)
    return torch.cat(normal_list, dim=0)
```

2. **网格面法向量**（用于网格生成时的偏置）。

### 2.4 装配体修改

每次优化迭代更新气腔形状时，`modify_assembly()` 会根据新的控制点坐标重新计算法向偏置，更新所有壳层节点位置：

```python
def modify_assembly(self, design_sensitivity_vars, assembly):
    super().modify_assembly(design_sensitivity_vars, assembly)
    
    # 重算法向偏移
    base_nodes = nodes[base_ids]
    target_nodes = self._compute_offset_targets(base_nodes, self._tri_local)
    disp = target_nodes - base_nodes

    # 更新各层节点
    for layer in range(1, self.num_layers + 1):
        alpha = float(layer) / float(self.num_layers)
        nodes[layer_ids] = base_nodes + alpha * disp
```

### 2.5 FEA 后处理：负高斯权重检测

偏置壳单元可能出现几何畸变导致高斯权重为负。`CodesignFEAParams.create_fea()` 中实现了检测逻辑：

```python
if (element_shell.gaussian_weight.min() < 0):
    # 输出法向量可视化用于调试
    raise ValueError("The Gaussian weights of the C3D6 elements "
                     "are negative. Please check the mesh quality.")
```

---

## 3. 外骨骼材料设计：SIMP 拓扑优化

### 3.1 SIMP 材料插值

基于变密度法的**固体各向同性材料惩罚（SIMP）** 模型，将连续的材料密度变量 $\rho \in [0, 1]$ 插值到材料属性：

$$
\mu(\rho) = \mu_{\min} + \rho^p (\mu_{\max} - \mu_{\min})
$$

$$
\kappa(\rho) = \kappa_{\min} + \rho^p (\kappa_{\max} - \kappa_{\min})
$$

其中：
- $p$ 为惩罚因子（`penalfactor`），通常取 $p \geq 1$ 以抑制中间密度
- $\mu_{\max}, \kappa_{\max}$ 为实体材料的最大模量
- $\mu_{\min} = \mu_{\max} \cdot \text{simp\_ratio\_min}$ 为避免数值奇异的极小值

**代码对应**（`simpmaterial.py`）：

```python
ratio = get_ratio(gaussian_points)  # ρ ∈ [0, 1]
mu = ratio * (mumax - mumax * simp_ratio_min) + mumax * simp_ratio_min
kappa = ratio * (kappamax - kappamax * simp_ratio_min) + kappamax * simp_ratio_min
```

### 3.2 B 样条材料场参数化

为获得连续的、可微的材料密度场，采用 B 样条场（BSP）参数化密度分布。这与几何参数化使用同一套底层技术：

```python
# 初始化 BSP 场
basis_x = bspmap.BasisClamped(num_cps=nx, degree=degree)
basis_y = bspmap.BasisClamped(num_cps=ny, degree=degree)
basis_z = bspmap.BasisClamped(num_cps=nz, degree=degree)

bsp = bspmap.BSP(basis=[basis_x, basis_y, basis_z], ...)
self.simp_field = bsp
self._cps = torch.from_numpy(bsp.control_points)  # 设计变量
```

材料密度场的控制点 $\mathbf{\Phi}_M$ 通过 B 样条基函数映射到任意空间点：

$$
\rho(\mathbf{x}) = \sum_{i,j,k} N_i(x) N_j(y) N_k(z) \cdot (\mathbf{\Phi}_M)_{ijk}
$$

### 3.3 空间导数信息

为改善优化的收敛性，`SIMPMaterials` 还提供了带空间导数的密度插值方法 `get_ratio_with_spatial_derivative()`，通过一阶泰勒展开构造代理近似，使得灵敏度信息在空间上更加光滑：

```python
def get_ratio_with_spatial_derivative(self, nodes):
    # 计算密度及其空间梯度
    rdx = Σ wdx * cps   # ∂ρ/∂x
    rdy = Σ wdy * cps   # ∂ρ/∂y
    rdz = Σ wdz * cps   # ∂ρ/∂z
    
    # 构造空间代理修正
    surrogate = rdx * x + rdy * y + rdz * z
    result = result + (surrogate - surrogate.detach())
    return result
```

### 3.4 SIMP 材料替换

在 `set_materials()` 中，标准 C3D4 单元被替换为自定义的 `SIMPElementC3D10` 类（继承自 C3D10 + Fscrw 正则化），同时根据高斯积分点位置查询密度场，为每个积分点分配独立的材料属性：

```python
def set_materials(self, fe):
    # 1. 替换单元类型（嵌入 Fscrw 正则化）
    elements_new = self.SIMPElementC3D10(elems_index=elements._elems_index,
                                          elems=elements._elems,
                                          penalfactor=self.penalfactor)
    
    # 2. 查询高斯积分点处的密度
    ratio = self.get_ratio(gaussian_points_locations)
    
    # 3. SIMP 插值
    mu = ratio * (mumax - mumax * simp_ratio_min) + mumax * simp_ratio_min
    kappa = ratio * (kappamax - kappamax * simp_ratio_min) + kappamax * simp_ratio_min
    
    # 4. 分配材料
    materials = NeoHookeanLnJ(mu=mu, kappa=kappa)
    elements_new.set_materials(materials)
```

### 3.5 CodesignMaterials 的壳材料处理

`CodesignMaterials` 继承自 `SIMPMaterials`，额外为壳单元（C3D6）设置均匀的材料属性：

```python
class CodesignMaterials(SIMPMaterials):
    def set_materials(self, fe):
        # 为壳单元设置均匀材料
        elements_shell = fe.assembly.get_part('final_model').elems['C3D6']
        mu = self.shell_mu      # 软材料剪切模量
        kappa = self.shell_kappa
        materials = NeoHookean(mu=mu, kappa=kappa)
        elements_shell.set_materials(materials)
        
        # 为实体单元设置 SIMP 材料
        super().set_materials(fe)   # 调用 SIMPMaterials.set_materials()
```

---

## 4. Fscrw 正则化方法

### 4.1 问题动机

在 SIMP 拓扑优化中，低密度区域的单元（$\rho \to 0$）刚度极低，容易产生**零能模式**（hourglass mode）—— 即单元在不产生应变能的情况下发生畸变。这会导致：
- 刚度矩阵奇异或病态
- 位移场出现非物理的锯齿振荡
- 灵敏度信息失真，优化收敛困难

### 4.2 Fscrw 正则化原理

Fscrw 正则化通过惩罚位移二阶梯度的**反对称分量**来抑制零能模式。其物理直觉是：零能模式通常伴随着位移场的快速空间振荡，而反对称二阶梯度恰好能捕捉这种振荡。

定义位移二阶梯度张量：

$$
U_{,ijk} = \frac{\partial^2 u_i}{\partial x_j \partial x_k}
$$

其反对称分量（仅涉及后两个指标 $j, k$）为：

$$
F^{\text{skew}}_{ijk} = U_{,ijk} - U_{,ikj}
$$

正则化能量为：

$$
E_{\text{reg}} = p \int_{\Omega} F^{\text{skew}}_{ijk} F^{\text{skew}}_{ijk} \,\mathrm{d}\Omega
$$

其中 $p$ 为正则化系数（`penalfactor`）。

### 4.3 代码实现

`SIMPElementFsrew` 类实现了 Fscrw 正则化，其 `potential_Energy` 在标准超弹性势能基础上叠加正则化项：

```python
class SIMPElementFsrew(torchfea.elements.Element_3D):
    def potential_Energy(self, RGC, rotation_matrix=None):
        # 1. 标准超弹性应变能
        Ea = super().potential_Energy(RGC, rotation_matrix)

        # 2. 计算位移二阶梯度
        Ugrad2 = torch.zeros([num_gauss, num_elems, 3, 3, 3])
        for i in range(num_nodes_per_elem):
            Ugrad2 += shape_func_d2[..., i] * U[elems[:, i]]

        # 3. 反对称分量
        Fskew = Ugrad2 - Ugrad2.transpose(2, 3)  # Fskew_{ijk} = U_{,ijk} - U_{,ikj}

        # 4. 正则化能量
        Er = penalfactor * torch.einsum('gIij,gIij,g->', Fskew, Fskew, gaussian_weight)

        return Ea + Er
```

### 4.4 切线刚度修正

对正则化能量求二阶变分，得到其对切线刚度矩阵的贡献。`_get_EpdUe_EpdUe2` 方法返回修正后的单元内力和切线刚度：

```python
def _get_EpdUe_EpdUe2(self, U, if_onlyforce=False):
    result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

    Ugrad2 = Σ shape_func_d2[i] * U[elems[:, i]]
    Fskew = Ugrad2 - Ugrad2.transpose(2, 3)

    # 正则化对内力（一阶变分）的贡献
    EmdUgrad2 = 4 * penalfactor * (Ugrad2 - Ugrad2.transpose(2, 3))
    EmdUe = torch.einsum('gIij,gija->aIe', EmdUgrad2, dN2W)

    # 正则化对切线刚度（二阶变分）的贡献
    # 在初始化时预计算（见 __init__ 中的 _EmdUe_2）

    return EmdUe + result0[0], self._EmdUe_2 + result0[1]
```

### 4.5 对比：Fgrad 正则化

`SIMPMaterials` 中还定义了另一种正则化方法 `SIMPElementFgrad`，其直接惩罚位移二阶梯度的 Frobenius 范数（而非仅反对称部分）：

$$
E_{\text{reg}}^{\text{Fgrad}} = p \int_{\Omega} U_{,ijk} U_{,ijk} \,\mathrm{d}\Omega
$$

相比之下，Fscrw 只惩罚**剪切类**的高频模式，而对**伸缩类**的高阶模式（如弯曲变形中的线性应变梯度）不加惩罚，因此对物理变形的干扰更小，是更优的选择。

### 4.6 正则化系数选择

系数 $p$（`penalfactor`）需根据问题特点选择：
- $p$ 过小 → 无法有效抑制零能模式
- $p$ 过大 → 过度刚化低密度区，影响最优拓扑

实践中通常取 $p = 0.01 \sim 0.1$，在代码中通过 `SIMPMaterials.__init__(penalfactor=...)` 设置。

---

## 5. 形状-材料联合优化模型

### 5.1 设计变量

联合优化问题的设计变量包含两类：

| 类别 | 符号 | 描述 | 维度 | 更新器 |
|-----|------|------|------|--------|
| 气腔控制点 | $\mathbf{\Phi}_G$ | 球面映射 CPGEO 的控制点坐标 | $\mathbb{R}^{N_G \times 3}$ | `UpdaterGeometries` |
| 材料密度场控制点 | $\mathbf{\Phi}_M$ | BSP 场控制点（密度值） | $\mathbb{R}^{N_M}$ | `UpdaterMaterials` |

### 5.2 目标函数

典型的目标函数是**最大化结构刚度**（即最小化总势能），可包含多工况加权：

$$
\mathcal{J} = \sum_{s=1}^{N_s} w_s \cdot \Pi_s(\mathbf{u}_s, \mathbf{\Phi}_G, \mathbf{\Phi}_M)
$$

其中 $\Pi_s$ 为第 $s$ 个载荷工况下的总势能，$w_s$ 为权重。

在 `twist.py` 示例中，扭矩工况的目标为两载荷步势能差：

```python
def objective_function(self):
    E0 = assembly._total_Potential_Energy(RGC=RGC0)  # 约束工况
    E1 = assembly._total_Potential_Energy(RGC=RGC1)  # 自由工况
    return E1 - E0  # 扭转释放的能量
```

### 5.3 材料体积约束

与经典拓扑优化类似，可在目标函数中嵌入体积分数约束或惩罚。例如 `ObjectiveFunction` 中可以计算当前体积分数：

```python
def get_volume_fraction(self):
    ratio_now = (mu - mumax * minratio) / (mumax * (1 - minratio))
    volume_fraction = (gaussian_weight * ratio_now).sum() / gaussian_weight.sum()
    return volume_fraction
```

### 5.4 联合更新策略

在每一步优化中，两类设计变量**共享同一组有限元分析结果**，但分别执行各自的子优化：

```
算法：协同优化单步
———————————————————————————————————
1. 生成几何（CPGEO）+ 构建偏置壳网格
2. 查询 SIMP 材料密度 → 分配材料
3. FEA 求解（Newton-Raphson）
4. 伴随法灵敏度分析（自动微分）
5. 将总梯度拆分为：
   ├── dJ/dΦ_G → UpdaterGeometries 子优化（L-BFGS + 几何约束）
   └── dJ/dΦ_M → UpdaterMaterials 子优化（L-BFGS + 材料约束）
6. 更新控制点 → 回到 1
———————————————————————————————————
```

---

## 6. 协同约束

协同优化需要处理两类特有的几何约束，确保壳结构的可制造性和数值稳定性。

### 6.1 内凹曲率约束（InwardCurvatureRadius）

偏置壳由气腔表面沿法向偏移得到。若气腔表面的**内凹曲率**过大，偏移面将产生自交，导致网格畸变。

约束定义为：

$$
k_{\text{inward}} \leq \frac{1}{t_{\text{eff}}}, \quad t_{\text{eff}} = t + m_{\text{ratio}} \cdot t + m_{\text{abs}}
$$

其中 $k_{\text{inward}} = \max(k_1^+, k_2^+)$ 取正主曲率（仅内凹方向），$t$ 为壳厚度。

主曲率计算采用第一、第二基本形式：

```python
@staticmethod
def _principal_curvatures(rdu, rdu2):
    I = torch.einsum("pim,pin->pmn", rdu, rdu)        # 第一基本形式
    II = torch.einsum("pimn,pi->pmn", rdu2, normal)    # 第二基本形式
    S = torch.linalg.solve(I, II)                       # 形状算子
    tr = S[..., 0, 0] + S[..., 1, 1]
    det = S[..., 0, 0] * S[..., 1, 1] - S[..., 0, 1] * S[..., 1, 0]
    k1, k2 = 0.5 * (tr ± sqrt(tr² - 4·det))            # 主曲率
    return k1, k2
```

### 6.2 偏移面最小距离约束（OffsetSurfaceMinThickness）

偏置壳的外表面在变形过程中可能与自身发生碰撞。该约束在偏移面上构建邻域图，约束相邻面片的距离不小于最小厚度。

在初始化时，通过 KD-Tree 搜索偏移面上的邻居对：

```python
def initialize(self, r0, rdu0, ...):
    roff = r0 + normal_sign * thickness * normals   # 偏移面
    tree = scipy.spatial.KDTree(roff.cpu().numpy())
    pairs = tree.query_pairs(r=search_radius)        # 邻居对
```

在每次调用时，根据法向夹角动态调整最小距离：

```python
mindist = dmin × opposition  # opposition 为法向量反平行程度
```

使用指数增强的障碍函数施加惩罚：

```python
violation = mindist - dist + barrier_thre
hard_boost = exp(hard_violation_beta × (rel_violation - 1))
loss += penalty_scale × penalty × hard_boost
```

### 6.3 几何约束汇总

MorphOpt codesign 中的约束体系：

| 约束 | 类名 | 作用 | 论文对应 |
|-----|------|------|---------|
| 内凹曲率 | `InwardCurvatureRadius` | 限制气腔内凹曲率 ≤ 1/厚度 | TRO2023 §IV-B |
| 偏移面距离 | `OffsetSurfaceMinThickness` | 防止偏移外表面自交 | 新增 |
| 曲面光顺 | `Fairness` | 切向角 + 切向量均匀性 | TRO2023 §IV-C |
| 曲面间距离 | `Distance` | 表面间最小距离 | TRO2023 §IV-A |
| 设计域边界 | `Cylinder` / `MinRadius` | 约束在设计域内 | TRO2023 §IV |
| 材料密度范围 | `MinValue` / `MaxValue` | $\rho \in [0.001, 0.999]$ | SIMP 标准 |

---

## 7. 灵敏度分析与自动微分

### 7.1 设计变量到装配体的映射

两类设计变量通过 `Params.obtain_design_sensitivity_vars()` 获取，并通过 `modify_assembly()` 应用到 FEA 模型：

```python
# 几何控制点 → 修改节点坐标
geometry.modify_assembly(dv['geometry'], assembly)

# 材料密度控制点 → 修改高斯点材料属性
materials.modify_assembly(dv['materials'], assembly)
```

### 7.2 联合灵敏度求解

单次 FEA 求解后，通过 `get_jacobian_sensitivity_multistep` 自动求导得到目标对所有设计变量的梯度：

```python
design_gradients = solver.get_jacobian_sensitivity_multistep(
    fe_results=self.fe_results,
    design_vars=torch.cat([Φ_G, Φ_M], dim=0),  # 统一拼接
    load_names=self.jacobian_needed,
    apply_func=apply_func,       # modify_assembly
    compute_objective_funcs=obj,  # objective_function
)
```

### 7.3 梯度分配

总梯度按设计变量索引拆分为几何梯度和材料梯度：

```python
grad_G = design_gradients[:len(Φ_G)]  # → UpdaterGeometries
grad_M = design_gradients[len(Φ_G):]  # → UpdaterMaterials
```

### 7.4 材料灵敏度平滑

`Sensitivity` 类（`updaters/materials/objectivefuncs/sensitivity.py`）将自动微分返回的梯度构造为材料子优化的线性代理目标：

```python
class Sensitivity(BaseObjective):
    def __call__(self, cps, *args, **kwargs):
        return ((cps - self._cp0) * self.sensitivity).sum() * self.factor
```

`DensityFieldMinimize` 提供轻微的正则化，推动密度场趋于零（节省材料）：

```python
class DensityFieldMinimize(BaseObjective):
    def __call__(self, cps, *args, **kwargs):
        return self.scale * (cps.sum() + 1)**2
```

---

## 8. 数值流程

### 8.1 完整优化循环

```
算法：Co-Design 协同优化
———————————————————————————————————
while 未收敛:
    # ---- 网格生成 ----
    1. 球面映射气腔（CPGEO）← Φ_G
    2. 生成 C3D4 四面体网格（实体域）
    3. 偏置壳构建（C3D6）← 气腔表面 + 厚度
    4. 创建偏移表面（气压加载面）
    
    # ---- 材料分配 ----
    5. BSP 场查询密度 ρ(x) ← Φ_M
    6. SIMP 插值：μ(ρ), κ(ρ)
    7. 壳单元分配均匀材料
    
    # ---- FEA ----
    8. Newton-Raphson 求解静力平衡
    
    # ---- 灵敏度 ----
    9. 目标函数计算
    10. 自动微分 + 伴随法 → dJ/dΦ_G, dJ/dΦ_M
    
    # ---- 几何子优化（UpdaterGeometries） ----
    11. 形状导数代理目标 + 几何约束罚项
    12. L-BFGS 子优化 ← dJ/dΦ_G
    13. 更新 Φ_G（气腔控制点）
    
    # ---- 材料子优化（UpdaterMaterials） ----
    14. 材料灵敏度代理目标 + 密度范围约束
    15. L-BFGS 子优化 ← dJ/dΦ_M
    16. 更新 Φ_M（密度场控制点）
    
    # ---- 曲面重建 ----
    17. 若达到重建间隔，执行球面映射重建
    
    # ---- 保存 ----
    18. 保存历史、可视化
———————————————————————————————————
```

### 8.2 代码架构对应

```
Controller                         → 优化主循环 (optcore/controller.py)
├── Params                         → 参数组合 (optcore/modelparams/params.py)
│   ├── Geometry (CodesignGeometry) → 气腔 CPGEO + 偏置壳 (codesign/geometry.py)
│   │   └── _build_shell_c3d6()    → C3D6 壳生成
│   │   └── modify_assembly()      → 更新节点坐标
│   ├── FEAParams (CodesignFEAParams) → FEA 参数 (codesign/feaparams.py)
│   │   └── create_fea()           → 壳单元校验
│   └── Materials (CodesignMaterials) → SIMP 材料 (codesign/material.py)
│       ├── SIMPElementC3D10       → C3D10 + Fscrw 正则化
│       ├── get_ratio()             → 密度查询
│       └── set_materials()         → 分配 μ(ρ), κ(ρ)
├── MorphSolver                    → FEA 求解 (optcore/solver.py)
├── ObjectiveFunction              → 目标函数 (由示例定义)
└── Updaters                       → 设计变量更新 (optcore/updaters/updaters.py)
    ├── UpdaterGeometries          → 几何子优化
    │   ├── ShapeDerivative         → 形状灵敏度代理
    │   ├── Fairness / Distance    → 几何约束
    │   ├── InwardCurvatureRadius   → 内凹曲率约束 (codesign/constraints.py)
    │   ├── OffsetSurfaceMinThickness → 偏移面距离约束 (codesign/constraints.py)
    │   └── Cylinder               → 边界约束
    └── UpdaterMaterials           → 材料子优化
        ├── Sensitivity             → 材料灵敏度代理
        ├── DensityFieldMinimize    → 密度正则化
        └── MinValue / MaxValue    → 密度范围约束
```

### 8.3 设计变量数量参考

以 `examples/codesign/twist.py` 为例：

| 变量 | 数量 | 描述 |
|-----|------|------|
| 气腔控制点 $\mathbf{\Phi}_G$ | 477 × 3 = 1,431 | 球面映射 CPGEO |
| 密度场控制点 $\mathbf{\Phi}_M$ | 51 × 51 × 51 = 132,651 | 3 阶 BSP 场 |

两类变量数量差异悬殊，因此分别执行子优化可以针对各自特点设置不同的步长和收敛条件。

---

## 9. 完整代码示例

### 9.1 示例脚本结构

以 `examples/codesign/twist.py` 为例，展示如何定义协同优化任务：

```python
import morphopt
import torch
import cpgeo

# 材料参数
mumax = 4.82          # 最大剪切模量（硬材料）
minratio = 1e-6       # 最小密度比

class ThisController(morphopt.Controller):

    # ---- 目标函数 ----
    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def objective_function(self):
            # 两个载荷步的势能差（扭转能量）
            E0 = assembly._total_Potential_Energy(RGC=RGC0)
            E1 = assembly._total_Potential_Energy(RGC=RGC1)
            return E1 - E0

    # ---- 参数定义 ----
    class Params(morphopt.Params):
        class GeometryParams(morphopt.codesign.CodesignGeometry):
            def __init__(self):
                super().__init__(fea_seed_size=2.5,
                                 thickness=2.5,      # 壳厚度 2.5mm
                                 num_layers=1)       # 单层壳
                self.add_surface(self.BSP.initialize_cylinder(...))
                self.add_surface(self.CPGEO.initialize_Sphere(...))

        class FEAParams(morphopt.codesign.CodesignFEAParams):
            def define_interface(self):
                self.add_fea_interface(self.PressureInterface(
                    instance_name='final_model',
                    surface_name='surface_1_offset'),  # 气压加载在偏移面
                    name='pressure_1')

        class MaterialParams(morphopt.codesign.CodesignMaterials):
            def __init__(self):
                super().__init__(
                    mumax=mumax, kappamax=mumax * 10,
                    simp_ratio_min=minratio,
                    bounding_box=[-25, 25, -25, 25, 0, 50],
                    simp_field_resolution=1.0, degree=3,
                    shell_mu=0.48, shell_kappa=4.8,   # 壳材料
                    penalfactor=1e-1)                  # Fscrw 系数

    # ---- 更新器 ----
    class Updater(morphopt.Updaters):
        class UpdaterGeometries(morphopt.UpdaterGeometries):
            def __init__(self, params):
                super().__init__(params, max_step_iter=100)
                self.add_objective_function(ShapeDerivative())
                self.add_constraints(Fairness(...))
                self.add_constraints(Distance(min_distance=...))
                self.add_constraints(InwardCurvatureRadius(geometry=params.geometry))
                self.add_constraints(OffsetSurfaceMinThickness(geometry=params.geometry))
                self.if_update = [False, True]  # 只更新气腔

        class UpdaterMaterials(morphopt.UpdaterMaterials):
            def __init__(self, params):
                super().__init__(params, max_step_iter=200, max_step_length=0.1)
                self.add_objective_function(Sensitivity())
                self.add_constraints(MinValue(xmin=0.001))
                self.add_constraints(MaxValue(xmax=0.999))
                self.if_update = True

if __name__ == '__main__':
    morphopt.start_optimization(device='cpu', restart_per_iteration=20)
```

### 9.2 其他 codesign 示例

`examples/codesign/` 中包含多个协同优化示例：

| 示例文件 | 目标 | 特点 |
|---------|------|------|
| `twist.py` | 最大化扭转角 | 3 重旋转对称气腔 + SIMP 骨架 |
| `twist_energy.py` | 最大化扭转释放能量 | 目标为势能差 |
| `elongate_stiffness.py` | 最大化伸长刚度 | 单向拉伸 |
| `contraction_energy.py` | 最大化收缩能量 | 负泊松比效应 |
| `positive_contraction.py` | 正收缩变形 | 对比验证 |

---

## 10. 参考文献

1. **Chen F, Song Z, et al.** *Morphological Design for Pneumatic Soft Actuators and Robots with Desired Deformation Behavior.* IEEE Transactions on Robotics, 2023. (TRO2023Morph)

2. **Bendsøe M P, Sigmund O.** *Topology Optimization: Theory, Methods, and Applications.* Springer, 2003.

3. **Sigmund O.** *A 99 line topology optimization code written in Matlab.* Structural and Multidisciplinary Optimization, 2001.

4. **Chen F, Song Z, et al.** *Continuum Jacobian based Computational Morphogenesis for Soft Robotic Workspace Optimization.* IEEE Transactions on Robotics, 2025. (TRO2025Jacobian)

5. **Maloisel G, Knoop E, Schumacher C, Bächer M.** *Automated Design of Pneumatic Soft Grippers.* ACM Trans. Graph., 2021.

6. **Shabana A A.** *Computational Continuum Mechanics.* Cambridge University Press, 2018.

7. **Zienkiewicz O C, Taylor R L, Zhu J Z.** *The Finite Element Method: Its Basis and Fundamentals.* 7th ed., Butterworth-Heinemann, 2013.

---

> **撰写说明**：本文档阐述了 MorphOpt codesign 子模块中气腔形态与 SIMP 外骨架材料**协同优化**的完整理论框架与实现细节。该方法将薄壁壳单元的几何精确仿真（C3D6 偏置）与变密度拓扑优化的材料高效分配（BSP + SIMP）统一在可微分优化流水线中，并通过 Fscrw 正则化保证数值稳定性。
