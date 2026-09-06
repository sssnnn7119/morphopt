# 气腔-外骨骼材料协同优化（Co-Design）

> 本文档阐述 MorphOpt 框架中气动软体机器人的气腔形状与外部骨架材料的**协同优化方法**。该方法在变形形态优化（TRO2023Morph）的基础上，引入基于 SIMP 的材料拓扑优化，并结合偏置壳单元技术实现薄壁气腔的高效仿真，形成一套完整的气-固耦合协同设计流程。
>
> **文档结构**：Part I（§1–§6）阐述理论动机与方法设计；Part II（§7–§11）聚焦实现细节与代码。

---

## 目录

**Part I — 理论与方法**

1. [研究动机与设计思路](#1-研究动机与设计思路)
2. [几何建模：可变形气腔与偏置壁面](#2-几何建模可变形气腔与偏置壁面)
3. [外骨骼材料设计：SIMP 拓扑优化](#3-外骨骼材料设计simp-拓扑优化)
4. [正则化方法：抑制低密度区零能模式](#4-正则化方法抑制低密度区零能模式)
5. [形状-材料联合优化模型](#5-形状-材料联合优化模型)
6. [协同约束](#6-协同约束)

**Part II — 实现细节**

7. [代码架构总览](#7-代码架构总览)
8. [关键实现细节](#8-关键实现细节)
9. [数值流程](#9-数值流程)
10. [完整代码示例](#10-完整代码示例)
11. [参考文献](#11-参考文献)

---

# Part I — 理论与方法

---

## 1. 研究动机与设计思路

### 1.1 问题背景

气动软体机器人的变形能力由两个因素共同决定：**气腔几何**（决定气体膨胀的方向）和**壁面刚度分布**（决定变形被如何约束和放大）。理想情况是像生物体一样——柔软的肌肉负责大范围运动，坚硬的骨骼提供支撑和力的高效传递——两者协同工作。

然而传统单一材料设计面临根本矛盾：
- **材料偏软** → 变形大，但承载弱，能量传递效率低，结构易失稳
- **材料偏硬** → 承载强，但变形小，驱动器做功受限
- **刚度均一** → 无法在同一结构内同时实现"该软的地方软、该硬的地方硬"

这意味着仅优化气腔几何而不改变材料空间分布，设计自由度是严重受限的。如果能**同时**设计气腔形状和外壁材料的空间刚度分布——让受压区高刚度以约束变形到目标方向，让非受压区低刚度以允许大变形——就能突破单一材料的性能天花板。

### 1.2 核心思路：两层设计

为解决上述问题，本文提出一种**双层协同设计**策略：



| 层级 | 网格类型 | 材料 | 功能 | 设计变量 |
|------|---------|------|------|---------|
| 内腔 | （空腔） | — | 气压驱动 | — |
| 密封壁 | C3D6 楔形单元（CPGEO 内侧） | 均匀软材料 | 承受气压、密封、传递载荷 | 跟随 CPGEO 形状（无独立变量） |
| **CPGEO 分界面** | — | — | **C3D4/C3D6 交界** | **腔体形状 $\mathbf{\Phi}_G$** |
| 外骨骼 | C3D4 四面体（CPGEO 外侧） | SIMP 变密度 | 约束变形、放大运动 | 密度场 $\mathbf{\Phi}_M$ |

### 1.3 关键挑战与解决方案

| 挑战 | 解决方案 | 代码位置 |
|------|---------|---------|
| 薄壁密封层需精确仿真 | **偏置壳单元**：CPGEO 曲面 + 法向偏置 → C3D6 楔形元 | `codesign/geometry.py` |
| 外骨骼需大范围拓扑优化 | **SIMP + BSP 场参数化** + **RAMP 惩罚插值** | `codesign/material.py` |
| 低密度区零能模式导致数值不稳定 | **Fskew 正则化**：惩罚位移二阶梯度反对称分量 + 逐高斯点自适应惩罚 | `simpmaterial.py` |
| 壳结构在优化中可能自交或畸变 | **内凹曲率约束** + **偏移面最小距离约束** | `codesign/constraints.py` |

### 1.4 问题形式化

联合优化目标是在气腔几何 $\mathbf{\Phi}_G$ 和材料密度场 $\mathbf{\Phi}_M$ 上优化系统的变形响应，同时满足平衡方程和可制造性约束。目标函数 $\mathcal{J}$ 可根据具体任务灵活定义，例如：

- **位移驱动**：最大化或匹配指定点的位移/转角
- **刚度驱动**：通过系统平衡态的**切线刚度矩阵**（Jacobian）调控特定方向的柔顺性或承载能力
- **能量驱动**：最大化气压驱动下释放的应变能（做功）
- **多目标组合**：上述目标的加权和

一般形式为：

$$
\min_{\mathbf{\Phi}_G, \mathbf{\Phi}_M} \mathcal{J}\bigl(\mathbf{u}(\mathbf{\Phi}_G,\mathbf{\Phi}_M),\; \mathbf{K}_T(\mathbf{\Phi}_G,\mathbf{\Phi}_M)\bigr), \quad \text{s.t.} \quad \mathbf{R}(\mathbf{u}, \mathbf{\Phi}_G, \mathbf{\Phi}_M) = \mathbf{0}
$$

其中 $\mathbf{u}$ 为位移场，$\mathbf{K}_T = \partial\mathbf{R}/\partial\mathbf{u}$ 为切线刚度矩阵（Jacobian），$\mathbf{R} = \mathbf{0}$ 为静力平衡方程。

---

## 2. 几何建模：可变形气腔与偏置壁面

### 2.1 整体架构

CPGEO 球面映射闭曲面定义了**C3D4 实体域与 C3D6 密封壁的分界面**。密封壁由 CPGEO 曲面沿**法向向内偏置**生成，使用 C3D6 楔形单元层叠构成薄壁气腔；CPGEO 曲面外侧则填充 C3D4 四面体网格，用于 SIMP 外骨骼拓扑优化。

```
完整的有限元模型（从内到外）=
  气腔（空腔）
  + C3D6 楔形单元层（偏置壳壁，均匀软材料，确保密封）
  + CPGEO 分界面 ← 控制点 $\mathbf{\Phi}_G$ 定义此界面形状
  + C3D4 四面体网格（实体域，SIMP 变密度外骨骼）
```

### 2.2 壳单元构建流程

偏置壳的构建以 CPGEO 分界面为起点，向**气腔侧（法向反向）**偏移生成密封壁：

1. **基底层提取**：将 CPGEO 分界面上的网格节点作为密封壁的基层（layer 0）
2. **层叠偏移**：对每一层 $l = 1, \dots, N_{\text{layer}}$，沿法向向内偏移生成新节点：
   $$
   \mathbf{x}^{(l)}_i = \mathbf{x}^{(0)}_i - \frac{l}{N_{\text{layer}}} \cdot t \cdot \mathbf{n}_i
   $$
   其中 $t$ 为密封壁总厚度，$\mathbf{n}_i$ 为基层节点处的单位法向量（指向 C3D4 侧）
3. **构建楔形单元**：连接相邻层节点，生成 C3D6 楔形单元，并在最内层创建偏移表面用于气压加载

### 2.3 法向量计算

法向量由 CPGEO 曲面参数化 $\mathbf{r}(u,v)$ 的切向量叉积解析给出：

$$
\mathbf{n} = \frac{\partial \mathbf{r}}{\partial u} \times \frac{\partial \mathbf{r}}{\partial v}
$$

网格生成和灵敏度分析共用同一套解析法向量，保证了形状灵敏度的连续性。

### 2.4 装配体修改（计算图保持）

每次灵敏度评估时，需要将目标对壳层节点坐标的梯度反向传播到 CPGEO 控制点。为此，在梯度计算前**重建偏置节点坐标的计算图**：

$$
\mathbf{x}^{(l)}_i(\mathbf{\Phi}_G) = \mathbf{x}^{(0)}_i(\mathbf{\Phi}_G) - \alpha_l \cdot t \cdot \mathbf{n}_i(\mathbf{\Phi}_G)
$$

其中负号表示向气腔侧（法向反向）偏移。整个链条（CPGEO 控制点 $\to$ 分界面节点 $\to$ 法向量 $\to$ 偏置节点）通过自动微分保持连接，使得后续伴随法可以正确反传梯度。实现细节见 §8.1。

### 2.5 负高斯权重检测

偏置壳单元可能出现几何畸变导致高斯权重为负，此时程序会报错并提示检查网格质量。

---

## 3. 外骨骼材料设计：SIMP 拓扑优化

### 3.1 B 样条材料场参数化

材料密度场采用 B 样条场（BSP）参数化，与几何参数化使用同一套底层技术。控制点 $\mathbf{\Phi}_M$ 通过 B 样条基函数映射到任意空间点，得到**设计场值** $\chi(\mathbf{x})$：

$$
\chi(\mathbf{x}) = \sum_{i,j,k} N_i(x) N_j(y) N_k(z) \cdot (\mathbf{\Phi}_M)_{ijk}
$$

其中 $N_i, N_j, N_k$ 为三个方向上的 B 样条基函数。$\chi$ 的取值范围无约束（$-\infty < \chi < \infty$），需经后续映射转化为物理密度。

### 3.2 设计场到密度的映射

设计场值 $\chi(\mathbf{x})$ 首先通过 Sigmoid 函数映射到 $(0, 1)$：

$$
\rho_{\text{raw}}(\mathbf{x}) = \frac{1}{1 + e^{-\chi(\mathbf{x})}}
$$

然后经 **RAMP（Rational Approximation of Material Properties）** 惩罚得到有效密度比：

$$
\rho_{\text{eff}} = \frac{\rho_{\text{raw}}}{1 + p (1 - \rho_{\text{raw}})}, \quad p = 8
$$

RAMP 相比传统幂律 SIMP 的优势在于：其在 $\rho_{\text{raw}} \to 0$ 时梯度更大，能更有效抑制中间密度。

最终材料模量为：

$$
\mu(\mathbf{x}) = \rho_{\text{eff}} \cdot (\mu_{\max} - \mu_{\min}) + \mu_{\min}
$$

$$
\kappa(\mathbf{x}) = \rho_{\text{eff}} \cdot (\kappa_{\max} - \kappa_{\min}) + \kappa_{\min}
$$

其中 $\mu_{\min} = \mu_{\max} \cdot \text{simp\_ratio\_min}$ 为避免数值奇异。

### 3.3 计算图完整性：空间导数代理

SIMP 密度场通过 BSP 场查询得到设计场值：$\chi(\mathbf{x}_g) = \sum N(\mathbf{x}_g) \cdot \mathbf{\Phi}_M$，其中 $\mathbf{x}_g$ 为高斯点坐标。再经 Sigmoid 和 RAMP 映射得到有效密度 $\rho(\chi)$。当气腔几何 $\mathbf{\Phi}_G$ 变化时，分界面附近的网格节点随之移动，导致其对应的高斯点位置 $\mathbf{x}_g(\mathbf{\Phi}_G)$ 也发生改变。这意味着设计场值 $\chi$ 实际上同时依赖于两类设计变量：

$$
\chi\bigl(\mathbf{x}_g(\mathbf{\Phi}_G),\; \mathbf{\Phi}_M\bigr)
$$

然而在标准的 BSP 场查询中，$\mathbf{x}_g$ 被视为常数（仅 $\mathbf{\Phi}_M$ 参与计算图），$\partial\chi/\partial\mathbf{\Phi}_G$ 这一路径被截断，导致自动微分给出的灵敏度**不完整**——几何变化对材料场的影响被遗漏。

为解决此问题，我们在密度插值中引入**一阶空间导数代理修正**，通过泰勒展开近似补充这部分缺失的梯度：

$$
\Delta\chi \approx \frac{\partial\chi}{\partial\mathbf{x}} \cdot \Delta\mathbf{x}(\mathbf{\Phi}_G)
$$

其中 $\partial\chi/\partial\mathbf{x}$ 由 BSP 场的空间导数解析给出，$\Delta\mathbf{x}$ 由几何控制点变化引起。修正项在计算图中保持连接，确保 $\chi$（进而 $\rho$）对 $\mathbf{\Phi}_G$ 的敏感性被正确反传，从而保证伴随法灵敏度结果的完整性。

### 3.4 材料分配流程

每次 FEA 求解前，标准 C3D4 单元被替换为嵌入正则化的自定义单元，根据高斯点位置查询密度场，为每个积分点分配独立的材料属性 $\mu(\mathbf{x}), \kappa(\mathbf{x})$ 和惩罚因子 $p(\mathbf{x})$（见 §4.2）。壳单元（C3D6）则分配均匀的软材料参数。具体实现见 §8.2。

---

## 4. 正则化方法：抑制低密度区零能模式

### 4.1 问题动机

在 SIMP 拓扑优化中，低密度区域的单元（$\rho \to 0$）刚度极低，容易产生**零能模式**（hourglass mode）—— 即单元在不产生应变能的情况下发生畸变。这会导致：
- 刚度矩阵奇异或病态
- 位移场出现非物理的锯齿振荡
- 灵敏度信息失真，优化收敛困难

为抑制此类模式，MorphOpt 提供了三种正则化策略，均通过惩罚位移二阶梯度来实现，并采用**每个高斯点独立的自适应惩罚系数**。

### 4.2 自适应惩罚因子

惩罚因子 $p(\mathbf{x})$ 控制在每个高斯点处正则化能量的强度。其不再是一个全局标量，而是通过平滑映射从设计场 $\chi$ 逐点计算。关键设计是：整个过渡区间定义在 $\chi$ 的**负半轴**（$\chi_{\min}=-6,\;\chi_{\max}=-5$），确保惩罚仅作用于弱材料区域：

$$
p(\mathbf{x}) = p_0 \cdot S\!\left(\frac{\chi_{\max} - \chi(\mathbf{x})}{\chi_{\max} - \chi_{\min}}\right), \quad S(\xi) = 6\xi^5 - 15\xi^4 + 10\xi^3
$$

其中 $S$ 为 Smoothstep 函数（$\mathcal{C}^1$ 连续），$p_0$ 为基准惩罚系数。该设计基于物理直觉：
- **实体区**（$\chi \gg 0$，$\rho \to 1$）：材料刚度大，零能模式不易出现 → $p \approx 0$
- **弱材料区**（$\chi \approx -5 \sim -6$，$\rho \ll 1$）：刚度极低，零能模式风险高 → $p$ 从 $0$ 光滑过渡到 $p_0$
- **void 区**（$\chi \ll -6$，$\rho \to 0$）：完全惩罚 → $p \approx p_0$

---

### 4.3 Fskew 正则化（推荐）

#### 4.2.1 原理

Fskew 正则化惩罚位移二阶梯度的**反对称分量**。零能模式通常伴随着位移场的快速空间振荡，而反对称二阶梯度恰好能捕捉这种振荡，同时不干扰物理变形中的对称部分（如弯曲应变梯度）。

定义位移二阶梯度张量：

$$
U_{,ijk} = \frac{\partial^2 u_i}{\partial x_j \partial x_k}
$$

其关于后两个指标 $j, k$ 的反对称分量为：

$$
F^{\text{skew}}_{ijk} = U_{,ijk} - U_{,ikj}
$$

正则化能量为：

$$
E_{\text{reg}} = \int_{\Omega} p(\mathbf{x}) \; F^{\text{skew}}_{ijk} F^{\text{skew}}_{ijk} \,\mathrm{d}\Omega
$$

其中 $p(\mathbf{x})$ 为逐高斯点的空间变化惩罚系数（§3.4），低密度区自动增大，高密度区自动归零。

实现中，正则化能量在单元 `potential_Energy()` 中叠加到超弹性应变能之上，同时 `_get_EpdUe_EpdUe2()` 给出了对应的内力（一阶变分）和切线刚度（二阶变分）修正。具体代码见 §8.3。

### 4.4 Fgrad 正则化（备选）

直接惩罚位移二阶梯度的**完整 Frobenius 范数**（而非仅反对称部分）：

$$
E_{\text{reg}}^{\text{Fgrad}} = \int_{\Omega} p(\mathbf{x}) \; U_{,ijk} U_{,ijk} \,\mathrm{d}\Omega
$$

该方法对弯曲变形中的线性应变梯度也会惩罚，对物理变形的侵入性略高于 Fskew。

### 4.5 HuHu\_LuLu 正则化（试验性）

`SIMPElementHuHu_LuLu` 仅惩罚位移二阶梯度的**迹（体积分量）**，等价于保留偏量部分以最小化对物理弯曲的干扰：

$$
E_{\text{reg}}^{\text{dev}} = \frac{1}{2} \int_{\Omega} p(\mathbf{x}) \left[ \sum_{i,j,k} (U_{,ijk})^2 - \frac{1}{3} \sum_{i,j} \Bigl( \sum_{k} U_{,ijk} \Bigr)^2 \right] \mathrm{d}\Omega
$$

其物理意义类似于弹性力学中将应变分解为体积和偏量部分。零能模式主要表现为等体积畸变（偏量主导），因此以偏量为目标的 Fskew 仍是最高效的选择。

---

### 4.6 单元组合与默认选择

默认单元组合为 `C3D10 + Fskew`。各选项及适用场景见 §8.3 中的代码实现与表格。所有正则化方法均支持每个高斯点独立的惩罚因子（§4.2）。

---

## 5. 形状-材料联合优化模型

### 5.1 设计变量

联合优化问题的设计变量包含两类：

| 类别 | 符号 | 描述 | 维度 | 更新器 |
|-----|------|------|------|--------|
| 气腔控制点 | $\mathbf{\Phi}_G$ | 球面映射 CPGEO 的控制点坐标 | $\mathbb{R}^{N_G \times 3}$ | `UpdaterGeometries` |
| 材料密度场控制点 | $\mathbf{\Phi}_M$ | BSP 场控制点（密度值） | $\mathbb{R}^{N_M}$ | `UpdaterMaterials` |

### 5.2 目标函数

典型的目标函数是最大化结构刚度（最小化总势能）或最大化做功（如扭转释放能量），可包含多工况加权：

$$
\mathcal{J} = \sum_{s=1}^{N_s} w_s \cdot \Pi_s(\mathbf{u}_s, \mathbf{\Phi}_G, \mathbf{\Phi}_M)
$$

体积分数 $\bar\rho = \frac{\int_\Omega \rho(\mathbf{x}) \, \mathrm{d}\Omega}{\int_\Omega \mathrm{d}\Omega}$ 可作为约束或惩罚项嵌入目标。

### 5.3 联合更新策略

在每一步优化中，两类设计变量**共享同一组有限元分析结果**，但分别执行各自的子优化。总梯度 $\nabla_{\mathbf{\Phi}}\mathcal{J}$ 通过伴随法一次性求得，然后按变量索引导出：

$$
\nabla_{\mathbf{\Phi}_G}\mathcal{J} \longrightarrow \text{UpdaterGeometries} \quad \text{(L-BFGS + 几何约束)}
$$
$$
\nabla_{\mathbf{\Phi}_M}\mathcal{J} \longrightarrow \text{UpdaterMaterials} \quad \text{(L-BFGS + 材料约束)}
$$

两个子优化交替或并行更新各自的设计变量，进入下一轮迭代。

---

## 6. 协同约束

协同优化需要处理两类特有的几何约束，确保壳结构的可制造性和数值稳定性。

### 6.1 内凹曲率约束（InwardCurvatureRadius）

偏置壳由气腔表面沿法向偏移得到。若气腔表面的**内凹曲率**过大，偏移面将产生自交，导致网格畸变。

约束定义为：

$$
k_{\text{inward}} \leq \frac{1}{t_{\text{eff}}}, \quad t_{\text{eff}} = t + m_{\text{ratio}} \cdot t + m_{\text{abs}}
$$

其中 $k_{\text{inward}} = \max(k_1^+, k_2^+)$ 取正主曲率（仅内凹方向），$t$ 为壳厚度。主曲率通过对曲面第一、第二基本形式求解形状算子的特征值得出。


### 6.2 偏移面最小距离约束（OffsetSurfaceMinThickness）

偏置壳的外表面在变形过程中可能与自身发生碰撞。该约束在偏移面上构建邻域图，约束相邻面片的距离不小于最小厚度。

初始化时通过 KD-Tree 搜索偏移面上的邻居对；每次调用时根据法向夹角动态调整最小距离，并使用指数增强的障碍函数施加惩罚：

$$
\mathcal{L}_{\text{dist}} = \sum_{(i,j) \in \mathcal{N}} \text{penalty}\bigl(d_{ij},\; d_{\min} \cdot \text{opposition}_{ij}\bigr)
$$

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

# Part II — 实现细节

---

## 7. 代码架构总览

### 7.1 文件组织

```
morphopt/
├── codesign/
│   ├── __init__.py
│   ├── geometry.py        ← 偏置壳构建、法向量、modify_assembly
│   ├── material.py        ← CodesignMaterials（SIMP + 壳材料组合）
│   ├── feaparams.py       ← CodesignFEAParams（FEA 参数定义）
│   └── constraints.py     ← InwardCurvatureRadius / OffsetSurfaceMinThickness
├── optcore/
│   ├── modelparams/materials/
│   │   └── simpmaterial.py ← SIMP_BSPFieldMaterials、SIMPElementFskew/Fgrad/...
│   ├── updaters/materials/
│   │   └── objectivefuncs/  ← Sensitivity、DensityFieldMinimize
│   └── solver.py           ← 伴随法灵敏度求解
└── myjobs/codesign/        ← 任务脚本（协同设计）
```

### 7.2 类继承链

```
SIMP_BSPFieldMaterials          ← 材料场基类（BSP + RAMP + 自适应惩罚）
  └── CodesignMaterials         ← 额外处理壳单元（C3D6）均匀材料

torchfea.elements.Element_3D
  ├── SIMPElementFskew          ← Fskew 正则化（推荐）
  ├── SIMPElementFgrad          ← Fgrad 正则化（备选）
  ├── SIMPElementHuHu_LuLu      ← 体积分量正则化（试验性）
  └── SIMPElementC3D10          ← C3D10 + Fskew 继承组合（默认）
         (C3D10, SIMPElementFskew)
```

### 7.3 数据流示意

```
Φ_G (CPGEO cps) ──→ modify_assembly() ──→ 壳层节点坐标
Φ_M (BSP cps)   ──→ set_materials()   ──→ μ(χ), κ(χ), p(χ)  @ 高斯点
                                         └─→ 替换为 SIMPElementC3D10
FEA 求解 ──→ 目标函数 ──→ 伴随法 ──→ dJ/dΦ_G + dJ/dΦ_M
                                        ├──→ UpdaterGeometries
                                        └──→ UpdaterMaterials
```

---

## 8. 关键实现细节

### 8.1 几何：偏置壳构建与计算图保持

#### 8.1.1 壳网格生成（`codesign/geometry.py`）

`_build_shell_c3d6()` 在初始网格划分时执行一次，以 CPGEO 分界面为起点向气腔侧偏置并构建 C3D6 楔形单元：

```python
def _build_shell_c3d6(self, part: torchfea.Part) -> torchfea.Part:
    # 获取 CPGEO 分界面上的三角网格（C3D4/C3D6 交界）
    tri_by_surface = {}
    for sidx in range(1, int(self.num_surface)):
        surf_name = f"surface_{sidx}_All"
        tri = part.surfaces.get_trimesh(surf_name)
        tri_by_surface[sidx] = tri

    # 对每一层，沿法向反向（向气腔侧）偏移生成节点
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

#### 8.1.2 解析法向量

CPGEO 曲面的 `get_normals()` 直接返回指向 C3D4 侧（外侧）的参数化法向量：

```python
def _compute_normals(self, base_nodes, tri_local):
    normal_list = []
    for sfidx in range(1, self.num_surface):
        normals = self.surface_list[sfidx].get_normals(surf_node_uv)
        normal_list.append(normals)
    return torch.cat(normal_list, dim=0)
```

#### 8.1.3 计算图保持

每次梯度评估时，`modify_assembly()` 重建偏置节点坐标的计算图，使 autograd 能反向传播到控制点：

```python
def modify_assembly(self, design_sensitivity_vars, assembly):
    super().modify_assembly(design_sensitivity_vars, assembly)
    
    # 当前控制点 → 曲面节点 → 法向偏置目标 → 壳层节点
    # 整个链条通过 autograd 保持连接
    base_nodes = nodes[base_ids]
    target_nodes = self._compute_offset_targets(base_nodes, self._tri_local)
    disp = target_nodes - base_nodes

    # 更新各层节点（计算图保留，用于后续灵敏度反传）
    for layer in range(1, self.num_layers + 1):
        alpha = float(layer) / float(self.num_layers)
        nodes[layer_ids] = base_nodes + alpha * disp
```

#### 8.1.4 负高斯权重检测

```python
if (element_shell.gaussian_weight.min() < 0):
    raise ValueError("The Gaussian weights of the C3D6 elements "
                     "are negative. Please check the mesh quality.")
```

---

### 8.2 材料：BSP 场 + RAMP + 自适应惩罚

#### 8.2.1 BSP 场初始化

```python
# 初始化 BSP 场
basis_x = bspmap.BasisClamped(num_cps=nx, degree=degree)
basis_y = bspmap.BasisClamped(num_cps=ny, degree=degree)
basis_z = bspmap.BasisClamped(num_cps=nz, degree=degree)

bsp = bspmap.BSP(basis=[basis_x, basis_y, basis_z], ...)
self.simp_field = bsp
self._cps = torch.from_numpy(bsp.control_points)  # 设计变量
```

#### 8.2.2 RAMP 密度插值

```python
def get_material_ratio(self, designfield):
    rho = 1 / (1 + torch.exp(-designfield))          # Sigmoid → (0, 1)
    rho_penalty = RAMP_interpolation(rho, p=8)       # RAMP 惩罚
    ratio = rho_penalty * (1 - self._simp_ratio_min) + self._simp_ratio_min
    return ratio

def RAMP_interpolation(rho, p):
    return rho / (1 + p * (1 - rho))
```

#### 8.2.3 空间导数代理（计算图补全）

高斯点位置随几何控制点 $\mathbf{\Phi}_G$ 变化，但标准 BSP 查询将其视为常数，截断了 $\chi$ 对 $\mathbf{\Phi}_G$ 的梯度路径。此修正通过一阶泰勒展开补充该缺失链路：

```python
def get_ratio_with_spatial_derivative(self, nodes):
    # 计算设计场值及其空间梯度
    rdx = Σ wdx * cps   # ∂χ/∂x
    rdy = Σ wdy * cps   # ∂χ/∂y
    rdz = Σ wdz * cps   # ∂χ/∂z
    
    # 构造空间代理修正：Δχ ≈ ∇χ · Δx
    # surrogate 的值参与前向计算，但其梯度被 detach 阻断，
    # 只保留位置变化 Δx 对结果的梯度路径
    surrogate = rdx * x + rdy * y + rdz * z
    result = result + (surrogate - surrogate.detach())
    return result
```

核心技巧 `result + (surrogate - surrogate.detach())` 保证前向结果不变，但 autograd 图中保留了高斯点坐标对 $\chi$ 的梯度路径，使得伴随法能正确反传 $\partial\mathcal{J}/\partial\mathbf{\Phi}_G$ 中经由材料场的贡献。

#### 8.2.4 自适应惩罚因子

```python
def get_penalty_factor(self, designfield):
    influence_max = -5          # χ ≥ -5  → 实体区，p ≈ 0
    influence_min = -6          # χ ≤ -6  → void 区，p ≈ p₀

    normalized = (influence_max - designfield) / (influence_max - influence_min)
    normalized = torch.clamp(normalized, 0.0, 1.0)

    # Smoothstep: C¹ 连续，-6→-5 区间内 0→1 光滑过渡
    penalty_factor = 6 * normalized**5 - 15 * normalized**4 + 10 * normalized**3
    return penalty_factor
```

#### 8.2.5 材料装配

```python
def set_materials(self, fe):
    # 替换单元类型（嵌入 Fskew 正则化）
    elements_new = self.SIMPElementC3D10(elems_index=elements._elems_index,
                                          elems=elements._elems,
                                          penalfactor=self.voidpenalfactor)
    
    # 查询高斯积分点处的密度
    designfield = self._map_bsp_designfield(gaussian_points_locations)
    ratio_now = self.get_material_ratio(designfield)
    
    # SIMP 插值
    mu = ratio_now * self._mumax
    kappa = ratio_now * self._kappamax
    
    # 分配材料
    materials = NeoHookeanLnJ(mu=mu, kappa=kappa)
    elements_new.set_materials(materials)
    
    # 每个高斯点独立惩罚因子
    elements_new.penalfactor = self.get_penalty_factor(designfield) * self.voidpenalfactor
```

#### 8.2.6 壳材料处理（`CodesignMaterials`）

```python
class CodesignMaterials(SIMP_BSPFieldMaterials):
    def set_materials(self, fe):
        # 为壳单元设置均匀材料
        elements_shell = fe.assembly.get_part('final_model').elems['C3D6']
        mu = self.shell_mu
        kappa = self.shell_kappa
        materials = NeoHookean(mu=mu, kappa=kappa)
        elements_shell.set_materials(materials)
        
        # 为实体单元设置 SIMP 材料
        super().set_materials(fe)
```

---

### 8.3 正则化：Fskew / Fgrad / HuHu_LuLu 单元实现

#### 8.3.1 Fskew（默认推荐）

```python
class SIMPElementFskew(torchfea.elements.Element_3D):
    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)

        self._dN2WP = torch.einsum('geija,ge->geija',
            self.shape_function_d2_gaussian,
            self.gaussian_weight * self.penalfactor)

        self._EmdUe_2 = torch.zeros([self.num_nodes_per_elem, 3,
                                      self.num_nodes_per_elem, 3,
                                      self._elems.shape[0]])
        for I0 in range(3):
            for i0 in range(3):
                for j0 in range(3):
                    # +4 项：δ_{IJ}δ_{ik}δ_{jl}
                    I, i, j, J, k, l = I0, i0, j0, I0, i0, j0
                    self._EmdUe_2[:, I, :, J, :] += \
                        torch.einsum('gea,geb->abe',
                            self._dN2WP[:, :, i, j, :],
                            self.shape_function_d2_gaussian[:, :, k, l, :]) * 4
                    # -4 项：δ_{Ii}δ_{Jk}δ_{jl}
                    I, i, j, J, k, l = I0, i0, j0, i0, I0, j0
                    self._EmdUe_2[:, I, :, J, :] -= \
                        torch.einsum('gea,geb->abe',
                            self._dN2WP[:, :, i, j, :],
                            self.shape_function_d2_gaussian[:, :, k, l, :]) * 4

    def potential_Energy(self, RGC, rotation_matrix=None):
        Ea = super().potential_Energy(RGC, rotation_matrix)

        Ugrad2 = torch.zeros([num_gauss, num_elems, 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += shape_func_d2[..., i] * U[elems[:, i]]

        Fskew = Ugrad2 - Ugrad2.transpose(2, 3)
        Er = torch.einsum('gIij,ge->', Fskew**2,
                          self.gaussian_weight * self.penalfactor)
        return Ea + Er

    def _get_EpdUe_EpdUe2(self, U, if_onlyforce=False):
        result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

        Ugrad2 = Σ shape_func_d2[i] * U[elems[:, i]]
        EmdUgrad2 = 4 * (Ugrad2 - Ugrad2.transpose(2, 3))
        EmdUe = torch.einsum('gIij,geija->aIe', EmdUgrad2, self._dN2WP)

        if if_onlyforce:
            return EmdUe + result0
        return EmdUe + result0[0], self._EmdUe_2 + result0[1]
```

#### 8.3.2 默认单元组合

```python
class SIMPElementC3D10(torchfea.elements.C3D10, SIMPElementFskew):
    pass
```

---

### 8.4 灵敏度分析与自动微分

#### 8.4.1 设计变量到装配体的映射

```python
# 几何控制点 → 修改节点坐标
geometry.modify_assembly(dv['geometry'], assembly)

# 材料密度控制点 → 修改高斯点材料属性
materials.modify_assembly(dv['materials'], assembly)
```

#### 8.4.2 联合灵敏度求解

单次 FEA 求解后，通过伴随法自动求导得到目标对所有设计变量的梯度：

```python
design_gradients = solver.get_jacobian_sensitivity_multistep(
    fe_results=self.fe_results,
    design_vars=torch.cat([Φ_G, Φ_M], dim=0),
    load_names=self.jacobian_needed,
    apply_func=apply_func,
    compute_objective_funcs=obj,
)
```

#### 8.4.3 梯度分配

```python
grad_G = design_gradients[:len(Φ_G)]  # → UpdaterGeometries
grad_M = design_gradients[len(Φ_G):]  # → UpdaterMaterials
```

#### 8.4.4 材料灵敏度平滑

`Sensitivity` 类将梯度构造为材料子优化的线性代理目标：

```python
class Sensitivity(BaseObjective):
    def __call__(self, cps, *args, **kwargs):
        return ((cps - self._cp0) * self.sensitivity).sum() * self.factor
```

`DensityFieldMinimize` 提供轻微正则化，推动密度场趋于零：

```python
class DensityFieldMinimize(BaseObjective):
    def __call__(self, cps, *args, **kwargs):
        return self.scale * (cps.sum() + 1)**2
```

---

## 9. 数值流程

### 9.1 完整优化循环

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
    5. BSP 场查询设计场 φ(x) ← Φ_M
    6. Sigmoid → RAMP(p=8) 惩罚插值：μ(φ), κ(φ)
    7. Smoothstep 映射 → 逐高斯点惩罚因子 p(φ)
    8. 壳单元分配均匀材料
    
    # ---- FEA ----
    9. Newton-Raphson 求解静力平衡
    
    # ---- 灵敏度 ----
    10. 目标函数计算
    11. 自动微分 + 伴随法 → dJ/dΦ_G, dJ/dΦ_M
    
    # ---- 几何子优化（UpdaterGeometries） ----
    12. 形状导数代理目标 + 几何约束罚项
    13. L-BFGS 子优化 ← dJ/dΦ_G
    14. 更新 Φ_G（气腔控制点）
    
    # ---- 材料子优化（UpdaterMaterials） ----
    15. 材料灵敏度代理目标 + 密度范围约束
    16. L-BFGS 子优化 ← dJ/dΦ_M
    17. 更新 Φ_M（密度场控制点）
    
    # ---- 曲面重建 ----
    18. 若达到重建间隔，执行球面映射重建
    
    # ---- 保存 ----
    19. 保存历史、可视化
———————————————————————————————————
```

### 9.2 代码架构对应

```
Controller                         → 优化主循环 (optcore/controller.py)
├── Params                         → 参数组合 (optcore/modelparams/params.py)
│   ├── Geometry (CodesignGeometry) → 气腔 CPGEO + 偏置壳 (codesign/geometry.py)
│   │   └── _build_shell_c3d6()    → C3D6 壳生成
│   │   └── modify_assembly()      → 更新节点坐标
│   ├── FEAParams (CodesignFEAParams) → FEA 参数 (codesign/feaparams.py)
│   │   └── create_fea()           → 壳单元校验
│   └── Materials (CodesignMaterials) → SIMP 材料 (codesign/material.py)
│       ├── SIMPElementC3D10       → C3D10 + Fskew 正则化
│       ├── get_material_ratio()    → Sigmoid + RAMP(p=8) 密度插值
│       ├── get_penalty_factor()    → Smoothstep 逐高斯点惩罚系数
│       └── set_materials()         → 分配 μ(φ), κ(φ) + penalfactor
├── Solver                    → FEA 求解 (optcore/solver.py)
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

### 9.3 设计变量数量参考

以 `myjobs/codesign/twist.py` 为例：

| 变量 | 数量 | 描述 |
|-----|------|------|
| 气腔控制点 $\mathbf{\Phi}_G$ | 477 × 3 = 1,431 | 球面映射 CPGEO |
| 密度场控制点 $\mathbf{\Phi}_M$ | 51 × 51 × 51 = 132,651 | 3 阶 BSP 场 |

两类变量数量差异悬殊，因此分别执行子优化可以针对各自特点设置不同的步长和收敛条件。

---

## 10. 完整代码示例

### 10.1 示例脚本结构

以 `myjobs/codesign/twist.py` 为例，展示如何定义协同优化任务：

```python
import morphopt
import torch
import cpgeo

# 材料参数
mumax = 4.82          # 最大剪切模量（硬材料）
minratio = 1e-6       # 最小密度比

class ThisController(morphopt.Controller):

    # ---- 目标函数 ----
    class ObjectiveFunction(morphopt.codesign.ObjectiveFunction):
        def objective_function(self):
            # 两个载荷步的势能差（扭转能量）
            E0 = assembly._total_Potential_Energy(RGC=RGC0)
            E1 = assembly._total_Potential_Energy(RGC=RGC1)
            return E1 - E0

    # ---- 参数定义 ----
    class Params(morphopt.codesign.Params):
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
    class Updater(morphopt.codesign.Updaters):
        class UpdaterGeometries(morphopt.codesign.UpdaterGeometries):
            def __init__(self, params):
                super().__init__(params, max_step_iter=100)
                self.add_objective_function(ShapeDerivative())
                self.add_constraints(Fairness(...))
                self.add_constraints(Distance(min_distance=...))
                self.add_constraints(InwardCurvatureRadius(geometry=params.geometry))
                self.add_constraints(OffsetSurfaceMinThickness(geometry=params.geometry))
                self.if_update = [False, True]  # 只更新气腔

        class UpdaterMaterials(morphopt.codesign.UpdaterMaterials):
            def __init__(self, params):
                super().__init__(params, max_step_iter=200, max_step_length=0.1)
                self.add_objective_function(Sensitivity())
                self.add_constraints(MinValue(xmin=0.001))
                self.add_constraints(MaxValue(xmax=0.999))
                self.if_update = True

if __name__ == '__main__':
    morphopt.start_optimization(device='cpu', restart_per_iteration=20)
```

### 10.2 其他 codesign 示例

`myjobs/codesign/` 中包含多个协同优化任务脚本：

| 示例文件 | 目标 | 特点 |
|---------|------|------|
| `twist.py` | 最大化扭转角 | 3 重旋转对称气腔 + SIMP 骨架 |
| `twist_energy.py` | 最大化扭转释放能量 | 目标为势能差 |
| `elongate_stiffness.py` | 最大化伸长刚度 | 单向拉伸 |
| `contraction_energy.py` | 最大化收缩能量 | 负泊松比效应 |
| `positive_contraction.py` | 正收缩变形 | 对比验证 |

---

## 11. 参考文献

1. **Chen F, Song Z, et al.** *Morphological Design for Pneumatic Soft Actuators and Robots with Desired Deformation Behavior.* IEEE Transactions on Robotics, 2023.

2. **Song Z, Chen F, et al.** *Continuum Jacobian based Computational Morphogenesis for Soft Robotic Workspace Optimization.* IEEE Transactions on Robotics, 2025.

---

> **撰写说明**：本文档阐述了 MorphOpt codesign 子模块中气腔形态与 SIMP 外骨架材料**协同优化**的完整理论框架与实现细节。该方法将薄壁壳单元的几何精确仿真（C3D6 偏置）与变密度拓扑优化的材料高效分配（BSP + SIMP）统一在可微分优化流水线中，并通过 Fskew 正则化保证数值稳定性。
