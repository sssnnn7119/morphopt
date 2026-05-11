# MorphOpt 优化理论

> 本文档结合两篇论文的核心理论与代码实现，系统阐述 MorphOpt 框架中软体机器人形态优化的数学原理与数值方法。

---

## 目录

1. [问题概述](#1-问题概述)
2. [几何表示](#2-几何表示)
3. [力学模型](#3-力学模型)
4. [优化问题建模](#4-优化问题建模)
5. [形状灵敏度分析](#5-形状灵敏度分析)
6. [工作空间优化与连续体雅可比矩阵](#6-工作空间优化与连续体雅可比矩阵)
7. [几何约束](#7-几何约束)
8. [子优化与信赖域方法](#8-子优化与信赖域方法)
9. [数值流程](#9-数值流程)
10. [参考文献](#10-参考文献)

---

## 1. 问题概述

气动软体机器人的变形行为由其**形态**（包括内部气腔形状和外部轮廓）决定。给定输入气压后，软体材料的柔性会产生连续大变形。形态设计的目标是**逆向求解**：给定期望的变形行为，自动确定最优的内外几何形状。

MorphOpt 框架要解决的核心问题可以分为两类：

| 问题类型               | 描述                                                                         | 对应论文        |
| ---------------------- | ---------------------------------------------------------------------------- | --------------- |
| **变形形态设计** | 给定目标变形（伸长量、弯曲角、扭转角或空间曲线），优化形状使实际变形趋近目标 | TRO2023Morph    |
| **工作空间优化** | 最大化末端执行器可达位置/姿态的集合（工作空间体积），同时优化形态与输入气压  | TRO2025Jacobian |

两类问题的共同技术基础包含：

- 自由曲面几何参数化（B 样条/球面映射）
- 非线性有限元分析（超弹性 Neo-Hookean 模型）
- 基于自动微分的离散伴随法灵敏度分析
- 高效的子优化策略（信赖域 + 拟牛顿法）

---

## 2. 几何表示

### 2.1 B 样条曲面（外表面与气腔表面）

对于需保持拓扑为圆柱壳的曲面（如机器人外表面），采用 **B 样条曲面** 进行参数化：

$$
\mathbf{r}(q,r) = \sum_{j=1}^{m} \sum_{i=1}^{n} \mathbf{P}_{ij}\, B_i^q(q)\, B_j^r(r)
$$

其中：

- $\mathbf{r} \in \mathbb{R}^3$ 为曲面上任意点
- $\mathbf{P}_{ij} \in \mathbb{R}^3$ 为控制点坐标
- $B_i^q, B_j^r$ 为 B 样条基函数（Cox-de Boor 递推公式）
- $(q,r)$ 为曲面参数坐标（纵向和环向）

B 样条的核心优势在于**局部支撑性**：调整一个控制点只会影响曲面局部区域，这为梯度优化提供了稀疏的灵敏度映射。

#### 代码对应

在 `src/morphopt/optcore/modelparams/geometry/geometryinterfaces/` 中，`BSP` 类实现了 B 样条曲面的初始化与操作，例如：

```python
self.add_surface(
    self.BSP.initialize_cylinder(
        r0=8., length=80., seed_size=1.0,
        symmetric=[1, [1]],
        flip=False, maxR=0.1, maxC=1.0,
        maxFF=0.2, perturbation_L=12.
    )
)
```

### 2.2 球面映射闭曲面（内嵌气腔）

对于需要**无缝闭合**的气腔曲面，B 样条在极点存在奇异性。MorphOpt 采用基于**球面映射**的闭曲面表示：

$$
\mathbf{r} = f(\mathbf{S}; \hat{\mathbf{\Phi}}, \hat{\boldsymbol{\phi}}) = \sum_{i=1}^{n} c_i(\mathbf{S}; \hat{\mathbf{\Phi}})\, \boldsymbol{\phi}^i, \quad \|\mathbf{S}\|_2 = 1
$$

其中：

- $\mathbf{S}$ 为单位球面上的参考点
- $\mathbf{\Phi}^i$ 为参考空间中的控制点（单位球面上）
- $\boldsymbol{\phi}^i$ 为配置空间中的控制点（实际 3D 坐标）
- $c_i$ 为归一化权重函数，由距离决定局部支撑：

$$
c_i(\mathbf{S}; \hat{\mathbf{\Phi}}) = \frac{C_i(\mathbf{S}; \mathbf{\Phi}^i)}{\sum_{j=1}^{n} C_j(\mathbf{S}; \mathbf{\Phi}^j)}
$$

初始权重采用 7 次多项式以保证处处三阶可导：

$$
C_i(\mathbf{S}; \mathbf{\Phi}^i) = 
\begin{cases}
20\bar{d}^{7} - 70\bar{d}^{6} + 84\bar{d}^{5} - 35\bar{d}^{4} + 1, & \bar{d}^i < 1 \\
0, & \bar{d}^i \ge 1
\end{cases}
$$

其中 $\bar{d}^i = d(\mathbf{S}, \mathbf{\Phi}^i)/d_0^i$ 为相对距离，$d_0^i$ 为第 $i$ 个控制点的影响半径（取第 $k$ 近邻距离）。

### 2.3 曲面重建算法

优化过程中控制点分布可能变得不均匀（局部过密或过稀），导致数值病态。MorphOpt 引入了**周期性曲面重建**算法：

1. **均匀播种**：在曲面上均匀采样新点，通过最小化弹簧势能实现均匀分布
2. **调和细化**：通过立体投影将点映射到平面，在平面上优化分布后再投影回球面
3. **匹配误差最小化**：求解线性最小二乘问题使新曲面与原始曲面匹配

$$
\min_{\hat{\boldsymbol{\psi}}} \sum_{m=1}^{n'} \left[\left\|\mathbf{r}^{m}_\text{opt} - f(\mathbf{\Psi}^{m}; \hat{\mathbf{\Psi}}, \hat{\boldsymbol{\psi}})\right\|^2 + \alpha \left\|\mathbf{r}^m_\text{opt} - \boldsymbol{\psi}^{m}\right\|^2\right]
$$

**代码对应**：`src/morphopt/codesign/geometry.py` 中的 `CPGEOinterface` 类实现了曲面重建逻辑。

---

## 3. 力学模型

### 3.1 超弹性本构

软体材料采用 **广义 Neo-Hookean 模型**，应变能密度为：

$$
W = \frac{\mu}{2}(\bar{I}_1 - 3) + \frac{\kappa}{2}(J - 1)^2
$$

其中：

- $\mu$ 为剪切模量，$\kappa$ 为体积模量
- $\bar{I}_1 = \text{tr}(\mathbf{F}\mathbf{F}^\text{T})J^{-2/3}$ 为第一正则化不变量
- $\mathbf{F}$ 为变形梯度，$J = \det(\mathbf{F})$ 为体积比

第一 Piola-Kirchhoff 应力张量为：

$$
s_{ij} = \frac{\partial W}{\partial F_{ji}} = \mu\left(\frac{1}{J^{2/3}}F_{ji} - \frac{1}{3}\bar{I}_1 F^{-1}_{ij}\right) + \kappa J(J-1)F^{-1}_{ij}
$$

**代码对应**：`examples/basic/shapeoptimization.py` 中设置材料参数：

```python
class MaterialParams(morphopt.Materials):
    def __init__(self):
        super().__init__(mu=0.482, kappa=4.8, density=1.08e-9)
```

### 3.2 虚功原理与平衡方程

系统的静力平衡由虚功原理描述：

$$
\mathcal{L}(\mathbf{u}, \mathbf{v}) = \mathcal{A}(\mathbf{u}, \mathbf{v}) - \sum_q \mathcal{B}^q(\mathbf{u}, \mathbf{v}) = 0, \quad \forall \mathbf{v} \in U
$$

其中：

- $\mathcal{A}$ 为内力虚功：$\displaystyle \mathcal{A}(\mathbf{u}, \mathbf{v}) = \int_{\Omega^0} s_{ij} \frac{\partial v_j}{\partial x_i} \mathrm{d}\Omega$
- $\mathcal{B}^q$ 为第 $q$ 个气腔的气压虚功：$\displaystyle \mathcal{B}^q(\mathbf{u}, \mathbf{v}) = -p_q \int_{\Gamma_{\text{in}}^{q,0}} (\mathbf{F}^{-1}\mathbf{v})^\text{T} \mathbf{m} J \mathrm{d}\Gamma$
- $\mathbf{u}$ 为真实位移场，$\mathbf{v}$ 为虚位移场
- $\Omega^0$ 为初始构型中的实体域

通过有限元离散（10节点二次四面体单元 C3D10），虚功方程转化为代数方程组：

$$
L_i(\mathbf{U}) = 0
$$

使用 Newton-Raphson 法迭代求解：

$$
\mathbf{U} \leftarrow \mathbf{U} - \mathbf{K}^{-1} \mathbf{L}, \quad K_{ij} = \frac{\partial L_i}{\partial U_j}
$$

**代码对应**：`src/morphopt/optcore/solver.py` 中 `MorphSolver.solve()` 方法：

```python
def solve(self):
    result = pools.apply_async(self._solve_FEA, ...)
    # 使用 torchfea 的隐式静力求解器
    result: torchfea.solver.StaticResult = fe.solve(...)
```

### 3.3 量纲分析

对于气动软体机器人，变形仅由**无量纲气压** $\tilde{p} = p/\mu$ 决定，与尺寸无关。这使得优化结果可跨尺度迁移。

---

## 4. 优化问题建模

### 4.1 变形形态设计（TRO2023Morph）

优化目标是使软体机器人在气压驱动下的变形趋近于期望构型：

$$
\min_{\mathbf{\Phi}} \mathcal{J} = \int_{\Gamma_{\text{RoI}}} \left[ w_{\text{pos}} \|\mathbf{z} - \mathbf{z}^*\|_2^2 + w_{\text{ori}} \|\log(\mathbf{R}^\text{T}\mathbf{R}^*)\|_\text{F}^2 \right] \mathrm{d}\Gamma
$$

其中：

- $\mathbf{z}, \mathbf{z}^*$ 为实际与目标位置
- $\mathbf{R}, \mathbf{R}^*$ 为实际与目标旋转矩阵
- $w_{\text{pos}}, w_{\text{ori}}$ 为权重系数
- 约束条件：平衡方程 $\mathcal{A}(\mathbf{u}, \mathbf{v}) - \mathcal{B}(\mathbf{u}, \mathbf{v}) = 0$

#### 代码对应

在 `examples/` 中，目标函数通过继承 `morphopt.ObjectiveFunction` 实现。例如在 `shapeoptimization.py` 中最大化末端轴向位移：

```python
class ObjectiveFunction(morphopt.ObjectiveFunction):
    def objective_function(self):
        return self.fe_results[0].GC[-2]  # 末端位移的 z 分量
```

### 4.2 工作空间优化（TRO2025Jacobian）

工作空间优化旨在最大化末端执行器的可达集合体积。工作空间分为：

| 类型             | 维度 | 符号                            | 描述                           |
| ---------------- | ---- | ------------------------------- | ------------------------------ |
| 平面位置工作空间 | 2D   | $2\text{A}0\text{R}2\text{T}$ | $x$-$z$ 平面内的可达区域   |
| 空间位置工作空间 | 3D   | $3\text{A}0\text{R}3\text{T}$ | 3D 可达位置空间                |
| 姿态工作空间     | 2D   | $3\text{A}2\text{R}0\text{T}$ | 末端指向方向（单位球面面积）   |
| 姿态工作空间     | 3D   | $3\text{A}3\text{R}0\text{T}$ | 末端旋转可达域（指数坐标体积） |
| 位姿耦合工作空间 | 3D   | $3\text{A}1\text{R}2\text{T}$ | 平面位置 + 面内转角            |

工作空间体积通过**散度定理**转化为边界积分：

**2D 位置工作空间**（$2\text{A}0\text{R}2\text{T}$）：

$$
|\mathbb{W}_\text{2T}| = \frac{1}{2} \oint_{\partial \mathbb{P}} \left(U_2 J^{1}_{\zeta_1} - U_1 J^{2}_{\zeta_1}\right) \mathrm{d}\zeta_1
$$

**3D 位置工作空间**（$3\text{A}0\text{R}3\text{T}$）：

$$
|\mathbb{W}_\text{3T}| = \frac{1}{3} \int_{\partial \mathbb{P}} \mathbf{U} \cdot (\mathbf{J}_{\zeta_1} \times \mathbf{J}_{\zeta_2}) \, \mathrm{d}\zeta_1 \mathrm{d}\zeta_2
$$

其中 $\mathbf{J}_{\zeta_k} = \partial \mathbf{U} / \partial \zeta_k$ 为边界上的雅可比向量。

**3D 姿态工作空间**（$3\text{A}3\text{R}0\text{T}$，使用指数坐标的近似）：

$$
|\mathbb{W}_\text{3R}| \approx \frac{1}{24} \int_{\partial \mathbb{P}} \bar{\mathbf{U}} \cdot (\bar{\mathbf{J}}_{\zeta_1} \times \bar{\mathbf{J}}_{\zeta_2}) \, \mathrm{d}\zeta_1 \mathrm{d}\zeta_2
$$

---

## 5. 灵敏度分析（基于自动微分的离散伴随法）

### 5.1 设计思路

在协同优化中，设计变量 $\mathbf{\Phi} = [\mathbf{\Phi}_G; \mathbf{\Phi}_M]$ 的维度可达 $10^5$ 量级。有限差分法求梯度需要逐变量摄动并重新执行非线性有限元分析，计算量不可接受。MorphOpt 采用 **基于 PyTorch 自动微分的离散伴随法** 计算精确梯度，整个灵敏度分析由底层的 `torchfea` 框架自动完成。

核心思路：设计变量 $\Phi_m$ 通过有限元装配过程（几何生成、材料插值、单元组装）影响系统，产生位移 $U_k$，位移进而决定目标函数 $\mathcal{J}$。利用链式法则和隐函数定理，通过引入**伴随变量**，将对 $M$ 个设计变量分别求导的 $M$ 次线性求解，压缩为对伴随变量的 **1--3 次线性求解**——与设计变量数量无关。

### 5.2 一阶伴随法：位移场灵敏度

#### 5.2.1 链式法则起点

设离散化后的静力平衡方程为：

$$
R_i(U_k, \Phi_m) = 0
$$

其中 $U_k$（$k = 1,\dots,N_{\text{dof}}$）为节点位移自由度，$\Phi_m$（$m = 1,\dots,M$）为设计变量，$R_i$ 为残差力向量。目标函数 $\mathcal{J}$ 依赖于位移解和设计变量：

$$
\mathcal{J} = \mathcal{J}(U_k, \Phi_m)
$$

由多元链式法则，全导数（灵敏度）为：

$$
\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} + \frac{\partial\mathcal{J}}{\partial U_k}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m}
\tag{5.1}
$$

第一项 $\partial\mathcal{J}/\partial\Phi_m$ 为显式依赖（如正则化项直接含 $\Phi_m$），可直接求偏导。第二项含 $\mathrm{d}U_k/\mathrm{d}\Phi_m$，即**位移对设计变量的隐式导数**——直接对每个 $m$ 求解需要 $M$ 次线性系统，不可行。

#### 5.2.2 隐函数定理求 $\mathrm{d}U_k/\mathrm{d}\Phi_m$

由于平衡方程 $R_i = 0$ 对任意设计均成立，其对 $\Phi_m$ 的全导数为零：

$$
\frac{\mathrm{d}R_i}{\mathrm{d}\Phi_m} = \frac{\partial R_i}{\partial U_k}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} + \frac{\partial R_i}{\partial\Phi_m} = 0
\tag{5.2}
$$

定义**切线刚度矩阵** $K_{ik} \equiv \partial R_i / \partial U_k$（已在前向 Newton-Raphson 收敛步完成组装和 $LDL^\mathrm{T}$ 分解）。由 (5.2) 得：

$$
K_{ik}\,\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} = -\frac{\partial R_i}{\partial\Phi_m}
\quad\Rightarrow\quad
\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} = -K_{kr}^{-1}\,\frac{\partial R_r}{\partial\Phi_m}
\tag{5.3}
$$

#### 5.2.3 伴随变量与总灵敏度

将 (5.3) 代入 (5.1)：

$$
\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} - \frac{\partial\mathcal{J}}{\partial U_k}\,K_{kr}^{-1}\,\frac{\partial R_r}{\partial\Phi_m}
\tag{5.4}
$$

引入**伴随变量** $\lambda_r$，定义为单个线性系统的解：

$$
\boxed{K_{rk}\,\lambda_r = -\frac{\partial\mathcal{J}}{\partial U_k}}
\tag{5.5}
$$

（已利用超弹性材料在保守载荷下 $K_{rk}=K_{kr}$ 的对称性。）等价地，$\lambda_r = -K_{rk}^{-1}\,\partial\mathcal{J}/\partial U_k$。代入 (5.4) 得到紧凑的**总灵敏度公式**：

$$
\boxed{\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} + \lambda_r\,\frac{\partial R_r}{\partial\Phi_m}}
\tag{5.6}
$$

#### 5.2.4 计算步骤总结

| 步骤 | 操作 | 计算量 |
|------|------|--------|
| **Step 1** | 自动微分求 $\partial\mathcal{J}/\partial U_k$ | 一次反向传播 |
| **Step 2** | 求解伴随方程 $K_{rk}\lambda_r = -\partial\mathcal{J}/\partial U_k$ | 一次前代/回代（复用已分解的 $K$） |
| **Step 3** | 计算 $\partial R_r/\partial\Phi_m$ 和 $\partial\mathcal{J}/\partial\Phi_m$ | 一次沿计算图反向传播 |
| **Step 4** | 组合为 $\mathrm{d}\mathcal{J}/\mathrm{d}\Phi_m$ | 内积，可忽略 |

整个过程只需求解**一次额外的线性方程组**，相比有限差分法计算量从 $\mathcal{O}(M \cdot N_{\text{dof}}^2)$ 降为 $\mathcal{O}(N_{\text{dof}}^2)$，与设计变量数量 $M$ 无关。

---

### 5.3 二阶伴随法：雅可比灵敏度

#### 5.3.1 问题扩展

对于工作空间优化和协同设计中涉及多工况气压组合的目标，目标函数可能不仅依赖位移 $U_i$，还依赖**连续体雅可比矩阵**——位移对载荷参数（气压）的导数：

$$
J_{in} \equiv \frac{\partial U_i}{\partial p_n}
\tag{5.7}
$$

此时目标函数扩展为：

$$
\mathcal{J} = \mathcal{J}(U_i,\, J_{in},\, \Phi_m)
\tag{5.8}
$$

链式法则新增一项：

$$
\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} + \frac{\partial\mathcal{J}}{\partial U_k}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} + \frac{\partial\mathcal{J}}{\partial J_{in}}\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m}
\tag{5.9}
$$

前两项由一阶伴随法处理。难点在第三项：需要雅可比矩阵本身对设计变量的导数 $\mathrm{d}J_{in}/\mathrm{d}\Phi_m$。

#### 5.3.2 雅可比矩阵的定解方程

对平衡方程 $R_j(U_i, \Phi_m, p_n) = 0$ 关于气压参数 $p_n$ 求偏导（固定 $\Phi_m$）：

$$
\frac{\partial R_j}{\partial U_i}\frac{\partial U_i}{\partial p_n} + \frac{\partial R_j}{\partial p_n} = 0
\quad\Rightarrow\quad
K_{ji}\,J_{in} + \frac{\partial R_j}{\partial p_n} = 0
\tag{5.10}
$$

即 $J_{in} = -K_{ij}^{-1}\,\partial R_j/\partial p_n$。这是 $J_{in}$ 必须满足的定解方程。

#### 5.3.3 雅可比矩阵对设计变量的全导数

对 (5.10) 关于设计变量 $\Phi_m$ 求全导数。注意 $K_{ji}$ 和 $\partial R_j/\partial p_n$ 同时显式依赖于 $\Phi_m$ 和隐式依赖于 $U_k(\Phi_m)$：

$$
\begin{aligned}
&K_{ji}\,\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} 
+ \left(\frac{\partial K_{ji}}{\partial\Phi_m} + \frac{\partial K_{ji}}{\partial U_k}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m}\right) J_{in} \\
+ &\left(\frac{\partial^2 R_j}{\partial\Phi_m\partial p_n} + \frac{\partial^2 R_j}{\partial U_k\partial p_n}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m}\right) = 0
\end{aligned}
\tag{5.11}
$$

引入关于 $p_n$ 的**全微分算子** $\mathrm{d}/\mathrm{d}p_n$：对任意 $Q(U_k(\Phi_m, p_n), \Phi_m, p_n)$，有 $\mathrm{d}Q/\mathrm{d}p_n =(\partial Q/\partial U_k)J_{kn} + \partial Q/\partial p_n$。利用此算子合并 (5.11) 中的同类项：

$$
K_{ji}\,\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} = -\frac{\mathrm{d}K_{jk}}{\mathrm{d}p_n}\,\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} - \frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_j}{\mathrm{d}p_n}\right)
\tag{5.12}
$$

代入 $\mathrm{d}U_k/\mathrm{d}\Phi_m = -K_{kr}^{-1}\,\partial R_r/\partial\Phi_m$（来自 (5.3)），并左乘 $K_{ij}^{-1}$：

$$
\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} = K_{ij}^{-1}\,\frac{\mathrm{d}K_{jk}}{\mathrm{d}p_n}\,K_{kr}^{-1}\,\frac{\partial R_r}{\partial\Phi_m} - K_{ij}^{-1}\,\frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_j}{\mathrm{d}p_n}\right)
\tag{5.13}
$$

#### 5.3.4 二阶伴随变量

将 (5.13) 代入 (5.9) 的第三项：

$$
\frac{\partial\mathcal{J}}{\partial J_{in}}\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial J_{in}}K_{ij}^{-1}\,\frac{\mathrm{d}K_{jk}}{\mathrm{d}p_n}\,K_{kr}^{-1}\,\frac{\partial R_r}{\partial\Phi_m} - \frac{\partial\mathcal{J}}{\partial J_{in}}K_{ij}^{-1}\,\frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_j}{\mathrm{d}p_n}\right)
\tag{5.14}
$$

为避免显式构造和存储庞大的三阶张量 $\mathrm{d}K_{jk}/\mathrm{d}p_n$，引入两个额外的伴随变量。**第一雅可比伴随变量** $\lambda_{rn}^*$：

$$
\boxed{K_{rj}\,\lambda_{rn}^* = -\frac{\partial\mathcal{J}}{\partial J_{jn}}}
\tag{5.15}
$$

即 $\lambda_{rn}^* = -K_{rj}^{-1}\,\partial\mathcal{J}/\partial J_{jn}$。

**第二雅可比伴随变量** $\lambda_i^{**}$，将 $\lambda_{rn}^*$ 与刚度矩阵的全导数缩并后作为右端项：

$$
\boxed{K_{is}\,\lambda_s^{**} = \frac{\mathrm{d}K_{rs}}{\mathrm{d}p_n}\,\lambda_{rn}^*}
\tag{5.16}
$$

即 $\lambda_s^{**} = K_{si}^{-1}\,(\mathrm{d}K_{ri}/\mathrm{d}p_n)\,\lambda_{rn}^*$。右端项按单元计算后组装，**无需**显式存储完整的 $\mathrm{d}K/\mathrm{d}p_n$ 张量。

代入 (5.14)，化简得：

$$
\frac{\partial\mathcal{J}}{\partial J_{in}}\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} = \lambda_i^{**}\,\frac{\partial R_i}{\partial\Phi_m} + \lambda_{rn}^*\,\frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_r}{\mathrm{d}p_n}\right)
\tag{5.17}
$$

#### 5.3.5 完整二阶伴随灵敏度

综合一阶伴随结果 (5.6) 和雅可比修正 (5.17)，得到**完整二阶伴随灵敏度公式**：

$$
\boxed{\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} + \lambda_r\,\frac{\partial R_r}{\partial\Phi_m} + \lambda_i^{**}\,\frac{\partial R_i}{\partial\Phi_m} + \lambda_{rn}^*\,\frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_r}{\mathrm{d}p_n}\right)}
\tag{5.18}
$$

四项的物理含义：

| 项次 | 表达式 | 物理含义 |
|------|--------|---------|
| ① | $\partial\mathcal{J}/\partial\Phi_m$ | 目标函数对设计变量的显式依赖 |
| ② | $\lambda_r\,\partial R_r/\partial\Phi_m$ | 位移-刚度耦合灵敏度（一阶伴随） |
| ③ | $\lambda_i^{**}\,\partial R_i/\partial\Phi_m$ | 雅可比-刚度耦合灵敏度（二阶伴随） |
| ④ | $\lambda_{rn}^*\,\partial(\mathrm{d}R_r/\mathrm{d}p_n)/\partial\Phi_m$ | 雅可比-载荷耦合灵敏度（一阶雅可比伴随） |

当目标函数不含雅可比依赖时（$\partial\mathcal{J}/\partial J_{in}=0$），有 $\lambda_{rn}^*=0$、$\lambda_i^{**}=0$，(5.18) 自动退化为 (5.6)。

#### 5.3.6 计算效率

三个伴随方程 (5.5)、(5.15)、(5.16) 共用同一个切线刚度矩阵 $K_{ij}$。前向 Newton-Raphson 求解时已完成 $LDL^\mathrm{T}$ 分解，每个伴随方程仅需一次前代/回代（$< 5\%$ 的前向求解耗时）。全部偏导数 $\partial R_i/\partial\Phi_m$ 和 $\partial(\mathrm{d}R_r/\mathrm{d}p_n)/\partial\Phi_m$ 通过一次沿计算图的反向传播获取——几何生成、材料插值、单元装配均表达为对 $\Phi_m$ 可微的张量操作。

**最终结论：无论设计变量数量 $M$ 多大，完整的二阶伴随灵敏度分析在每一次外层迭代中仅需 1--3 次额外的线性求解，计算量与 $M$ 无关。**

### 5.4 MorphOpt 中的灵敏度工作流

在 MorphOpt 框架中，上述推导由 `sensitivity_analysis()` 自动完成：

1. **获取设计变量**：调用 `params.obtain_design_sensitivity_vars()` 将几何控制点 $\mathbf{\Phi}_G$ 和材料密度控制点 $\mathbf{\Phi}_M$ 拼接为统一的设计向量。
2. **定义可微映射**：`apply_func` 回调将设计变量应用到装配体（修改节点坐标、更新材料属性），所有操作保持 PyTorch 计算图可追踪。
3. **调用灵敏度求解器**：`solver.get_jacobian_sensitivity_multistep()` 自动完成：
   - 自动微分计算 $\partial\mathcal{J}/\partial U_k$ 和 $\partial\mathcal{J}/\partial J_{in}$
   - 组装并求解伴随方程组 (5.5)、(5.15)、(5.16)
   - 沿计算图反向传播计算全部偏导数
   - 按 (5.18) 组合为总灵敏度 $\mathrm{d}\mathcal{J}/\mathrm{d}\Phi_m$
4. **梯度拆分**：总梯度按几何-材料边界拆分，分别送入 `UpdaterGeometries` 和 `UpdaterMaterials` 子优化器。

**代码对应**：`src/morphopt/optcore/objfunc.py` 中的 `ObjectiveFunction.sensitivity_analysis()` 方法。

### 5.5 灵敏度从 FEA 节点到控制点的映射

`torchfea` 返回的灵敏度梯度定义在 FEA 网格节点上。为将其映射到 B 样条/球面映射曲面的控制点上，MorphOpt 通过 `ShapeDerivative` 类进行**空间插值**：

```python
class ShapeDerivative(BaseObjective):
    def initialize(self, gradient, r0, ...):
        # gradient: torchfea 返回的节点灵敏度
        # 使用 scipy.interpolate.griddata 最近邻插值
        self.sensitivity = self._sensitivity_interpolation(
            Ldot=gradient.reshape([-1, 3]),
            points_request=torch.cat(self._cp0, dim=0),
            interpolated_points=interpolate_points
        )
```

**代码对应**：`src/morphopt/optcore/updaters/geometry/objectivefuncs/shapederivative.py`。

---

## 6. 工作空间优化与连续体雅可比矩阵

### 6.1 连续体雅可比定义

对于软体机器人，其运动学是**隐含的**（由非线性连续介质力学决定），无法写出显式正运动学。为此，定义**连续体雅可比矩阵**：

$$
J^i_{p_r} = \frac{\partial U_i}{\partial p_r}
$$

其中 $U_i$ 是末端执行器的第 $i$ 个自由度（3个平动 + 3个转动），$p_r$ 是第 $r$ 个气腔的气压。

这一雅可比将工作空间体积分从未知的构型空间映射到预设的气压空间：

$$
|\mathbb{W}| = \int_{\mathbb{W}} \mathrm{d}\mathbf{U} = \int_{\partial \mathbb{P}} w(\mathbf{U}, \mathbf{J}) \,\mathrm{d}\zeta
$$

### 6.2 高斯求积数值实现

连续积分通过高斯求积离散为加权求和：

$$
\max_{\boldsymbol{\phi}} \mathcal{T} = \sum_{g=1}^{k} \tau^g w_X(\mathbf{U}^g, \mathbf{J}^g)
$$

其中 $\tau^g$ 为高斯权重，$\mathbf{U}^g, \mathbf{J}^g$ 为第 $g$ 个气压条件下的变形与雅可比。不同工作空间问题的高斯点数量不同：

| 工作空间类型                    | 高斯点数 | 描述                  |
| ------------------------------- | -------- | --------------------- |
| $2\text{A}0\text{R}2\text{T}$ | 4        | 边界上的 2 点高斯积分 |
| $3\text{A}0\text{R}3\text{T}$ | 6        | 利用对称性减少        |
| $3\text{A}2\text{R}0\text{T}$ | 2        | 边界曲线上的积分      |
| $3\text{A}3\text{R}0\text{T}$ | 8        | 无对称性的全面积分    |
| $3\text{A}1\text{R}2\text{T}$ | 24       | 无对称性的全面积分    |

### 6.3 工作空间形状设计扩展

通过引入非均匀权重函数，工作空间优化可扩展到**形状设计**，例如在期望的姿态区域赋予更高权重，使优化结果偏向特定区域的工作空间。

---

## 7. 几何约束

为确保优化结果的**可制造性**和**数值稳定性**，MorphOpt 集成了多种几何约束，均以**罚函数**形式加入子优化问题。

### 7.1 最小距离约束

防止不同表面之间或同一表面自身发生穿透和过度减薄：

$$
g(\mathbf{r}^m, \mathbf{r}^n) = t^*_{mn} - \|\mathbf{r}^m - \mathbf{r}^n\| \leq 0
$$

导数为：

$$
\frac{\partial g}{\partial \mathbf{P}_{ij}} = -\frac{B_i^q B_j^r (\mathbf{r}^m - \mathbf{r}^n)}{\|\mathbf{r}^m - \mathbf{r}^n\|}
$$

**代码对应**：`src/morphopt/optcore/updaters/geometry/objectivefuncs/distancesurface.py` 中的 `Distance` 类。

### 7.2 曲率约束

限制主曲率 $k_1, k_2$ 以防止应力集中和网格畸变：

$$
h_1(q,r) = \frac{1}{2}(k_1^2 + k_2^2) = 2H^2 - K
$$

其中 $H$ 为平均曲率，$K$ 为高斯曲率。

在 `codesign` 子模块中还有面向壳结构的**向内曲率半径约束**，确保偏移曲面不产生自交：

```python
class InwardCurvatureRadius(BaseConstraints):
    """约束向内主曲率: k_inward <= 1 / (thickness + margin)"""
```

### 7.3 曲面光顺性约束

**角度约束**：惩罚切向量偏离正交：

$$
h_2(q,r) = \cos^2(\theta) = \frac{F^2}{EG}
$$

**均匀性约束**：惩罚切向量长度的梯度，使控制点分布均匀：

$$
h_3(q,r) = \frac{E_q^2 + E_r^2}{4\tau_q^2 E^2} + \frac{G_q^2 + G_r^2}{4\tau_r^2 G^2}
$$

**代码对应**：`src/morphopt/optcore/updaters/geometry/objectivefuncs/surfacefairness.py` 中的 `Fairness` 类。

### 7.4 边界约束

限制曲面在设计域内（如圆柱边界）：

```python
class Cylinder(BaseConstraints):
    """约束点在圆柱 (radius, height, bottom) 内"""
```

**代码对应**：`src/morphopt/optcore/updaters/geometry/objectivefuncs/boundarys.py`。

### 7.5 罚函数形式

所有约束通过统一的**障碍函数**转化为无约束问题：

$$
f(x) = 
\begin{cases}
0, & x \leq 0 \\
x^b, & x > 0
\end{cases}
$$

其中 $b=5$ 保证直到 4 阶导数连续。

---

## 8. 子优化与信赖域方法

### 8.1 动机

FEA 是计算瓶颈（单次求解可能耗时数分钟）。MorphOpt 采用**信赖域方法**减少 FEA 调用频率：在信赖域内用一阶泰勒展开构造代理函数代替真实 FEA，仅当子优化收敛后才重新执行 FEA。

### 8.2 子优化问题

子优化问题定义为：

$$
\min_{\vec{\Psi}} \tilde{\mathcal{L}}^k = \underbrace{\frac{\partial \mathcal{L}}{\partial \mathbf{\Phi}}^k \cdot \vec{\Psi}}_{\text{代理目标}} + \underbrace{\sum \text{Penalty}(\text{约束})}_{\text{约束罚项}}
$$

其中 $\vec{\Psi} = \mathbf{\Phi}^{k+1} - \mathbf{\Phi}^k$ 为设计变量的变化量。

### 8.3 L-BFGS 求解器

子优化采用 **有限记忆 BFGS（L-BFGS）** 方法：

$$
\vec{\Psi}^{l+1} = \vec{\Psi}^l - \alpha_l B_l^{-1} \nabla \tilde{\mathcal{L}}^k
$$

其中 $B_l$ 为 Hessian 矩阵的近似（通过 DFP 公式更新）：

$$
B^{-1}_{l+1} = B^{-1}_l + \frac{\mathbf{s}_l \mathbf{s}_l^\text{T}}{\mathbf{y}_l^\text{T} \mathbf{s}_l} - \frac{B^{-1}_l \mathbf{y}_l \mathbf{y}_l^\text{T} B^{-1}_l}{\mathbf{y}_l^\text{T} B^{-1}_l \mathbf{y}_l}
$$

$\mathbf{s}_l = \vec{\Psi}^{l+1} - \vec{\Psi}^l$ 为步长向量，$\mathbf{y}_l$ 为梯度变化向量。

**代码对应**：`src/morphopt/optcore/updaters/optimizer.py` 中的 `LBFGS` 类：

```python
class LBFGS(BaseOpt):
    def Hg_loop(self, dv):
        # 两循环递归计算 Hv 乘积
        q = dv.clone()
        for i in reversed(range(len(self.SK))):
            alpha[i] = self.rhok[i] * self.SK[i].dot(q)
            q = q - alpha[i] * self.YK[i]
        # ...
  
    def step(self, x_now, gk_now=None):
        # 确定搜索方向 dk
        # 回溯线搜索确定步长 alpha
        # 更新 BFGS 历史
```

### 8.4 回溯线搜索

步长 $\alpha_l$ 通过满足 Armijo 条件的回溯搜索确定：

$$
f(\mathbf{x} + \alpha \mathbf{d}) < f(\mathbf{x}) + c_1 \alpha \nabla f(\mathbf{x})^\text{T} \mathbf{d}
$$

### 8.5 收敛判据与自适应策略

子优化收敛判据（二选一）：

- $\alpha_k < \epsilon_\alpha$（步长过小）
- $l > \aleph^k$（达到最大迭代上限）

最大迭代次数 $\aleph^k$ 根据梯度变化自适应调整：

$$
\aleph^{k+1} = 
\begin{cases}
\beta_1 \aleph^k, & \lambda \leq 0.2 \\
\beta_2 \aleph^k, & \lambda > 0.2
\end{cases}
, \quad 
\lambda = \frac{\|\nabla \tilde{\mathcal{L}}^{k+1} - \nabla \tilde{\mathcal{L}}^{k}\|_1}{\|\nabla \tilde{\mathcal{L}}^{k}\|_1}
$$

梯度变化快 → 减少子优化迭代 → 更频繁执行 FEA（$\beta_2 = 0.9$）
梯度变化慢 → 增加子优化迭代 → 减少 FEA 频率（$\beta_1 = 1.2$）

---

## 9. 数值流程

### 9.1 整体优化循环

```
算法：MorphOpt 形态优化流程
———————————————————————————————————
while 未收敛:
    # 1. 几何建模
    根据控制点生成 B 样条曲面/球面映射曲面
    导出几何文件（STP）用于网格生成
  
    # 2. 有限元分析
    使用 GMSH 生成四面体网格（C3D10H）
    应用 Neo-Hookean 材料模型
    施加载荷（气压）与边界条件
    求解静力平衡（Newton-Raphson）
  
    # 3. 灵敏度分析（自动微分）
    获取设计变量（控制点坐标）
    定义 apply_func：设计变量 → 修改装配体
    定义 compute_objective_func：目标函数
    调用 solver.get_jacobian_sensitivity_multistep()
    ├── 自动微分求 ∂Obj/∂U
    ├── 求解伴随方程（复用刚度矩阵分解）
    └── 自动回传梯度至控制点
  
    # 4. 子优化（信赖域）
    构建代理函数（一阶泰勒展开 + 约束罚项）
    L-BFGS 迭代求解子问题
    回溯线搜索确定步长
  
    # 5. 更新与保存
    更新控制点坐标
    求解 ShapeDerivative 插值
    保存历史记录
    每若干步执行曲面重建
———————————————————————————————————
```

### 9.2 代码架构对应

```
Controller                    → 优化主循环控制 (optcore/controller.py)
├── Params                    → 参数管理 (optcore/modelparams/params.py)
│   ├── GeometryParams        → 几何参数 (BSP/球面映射)
│   ├── FEAParams             → FEA 参数（加载步、BC、RP）
│   └── Materials             → 材料参数（μ, κ, ρ）
├── MorphSolver               → FEA 并行求解 (optcore/solver.py)
│   └── torchfea.solver       → 隐式静力求解器 + 伴随求解
├── ObjectiveFunction         → 目标函数 + 灵敏度分析 (optcore/objfunc.py)
│   ├── compute_multistep_objective() → 多工况目标定义
│   ├── sensitivity_analysis()        → 自动微分灵敏度求解
│   │   └── solver.get_jacobian_sensitivity_multistep()
│   │       ├── apply_func (修改装配体)
│   │       ├── compute_objective_funcs (目标回调)
│   │       ├── 自动伴随求解 (复用 K 矩阵分解)
│   │       └── autograd 回传梯度至控制点
│   └── Jacobian                  → 结果中的雅可比信息 (fe_result.jacobian)
└── Updaters                  → 设计变量更新 (optcore/updaters/updaters.py)
    ├── UpdaterGeometries     → 几何更新 + 约束 (updaters/geometry/update_geometry.py)
    │   ├── ShapeDerivative   → 形状导数目标 (objectivefuncs/shapederivative.py)
    │   ├── Distance          → 最小距离约束 (objectivefuncs/distancesurface.py)
    │   ├── Fairness          → 曲面光顺约束 (objectivefuncs/surfacefairness.py)
    │   └── Cylinder/MinRadius → 边界约束 (objectivefuncs/boundarys.py)
    └── LBFGS                 → 子优化求解器 (updaters/optimizer.py)
```

> 测试环境：Intel Core i9-12900K, NVIDIA Titan V, 128 GB RAM。

---

## 10. 参考文献

1. **Chen F, Song Z, Chen S, Gu G, Zhu X.** *Morphological Design for Pneumatic Soft Actuators and Robots with Desired Deformation Behavior.* IEEE Transactions on Robotics, 2023. (`TRO2023Morph`)
2. **Chen F, Song Z, et al.** *Continuum Jacobian based Computational Morphogenesis for Soft Robotic Workspace Optimization.* IEEE Transactions on Robotics, 2025. (`TRO2025Jacobian`)
3. Choi K K, Kim N-H. *Structural Sensitivity Analysis and Optimization 1: Linear Systems.* Springer, 2006.
