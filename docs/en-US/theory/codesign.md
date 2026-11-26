# Co-design of pneumatic cavities and exoskeleton materials

[简体中文](../../zh-CN/theory/codesign.md)

> MorphOpt optimizes the cavity geometry and the material distribution of an external skeleton together. The formulation extends shape optimization with SIMP material interpolation. Offset layers represent the thin cavity wall in the finite-element model.
>
> **Document structure**: Part I (§1–§6) discusses the theoretical motivations and method design; Part II (§7–§11) focuses on the implementation details and code.

---

## Contents

<!-- docs:toc depth=1 -->

**Part I – Theories and Methods**

- [1 Research motivations and design considerations](#section-研究动机与设计思路)
- [2 Geometric modeling: deformable air cavities and offset walls](#section-几何建模可变形气腔与偏置壁面)
- [3 Exoskeleton material design: SIMP topology optimization](#section-外骨骼材料设计simp-拓扑优化)
- [4 Regularization methods: Suppressing zero-energy modes in low-density regions](#section-正则化方法抑制低密度区零能模式)
- [5 Shape-material combined optimization model](#section-形状-材料联合优化模型)
- [6 Coordination constraints](#section-协同约束)

**Part II – Implementation Details**

- [7 Overview of Code Architecture](#section-代码架构总览)
- [8 Key implementation details](#section-关键实现细节)
- [9 Numerical processes](#section-数值流程)
- [10 Complete code example](#section-完整代码示例)
- [11 References](#section-参考文献)

<!-- /docs:toc -->

---

# Part I – Theories and Methods

---

<a id="section-研究动机与设计思路"></a>

## 1 Research motivations and design considerations

<a id="section-问题背景"></a>

### 1.1 Problem background

The deformation response of the pneumatic soft robot is determined by both **Cavity geometry** and **Wall stiffness distribution**. The geometry of the air cavity affects the location and direction of the pressure load, while the distribution of wall stiffness influences the structural flexibility, deformation patterns, and load transfer. Collaborative design involves adjusting both types of design variables to meet the requirements of movement and load-bearing capabilities.

In the design of single-material structures, there is a trade-off between the ability to deform and the load-bearing capacity of the material.

- A lower material stiffness allows for greater deformation, but it may also reduce the load-bearing capacity and stability of the structure.
- A higher material stiffness increases the constraint on deformation, and may also limit the allowable driving displacement.
- The uniform stiffness distribution throughout the space restricts the ability to independently adjust local flexibility and support properties.

The combined optimization of the shape of the air cavity and the spatial distribution of materials expands the range of adjustable design variables. The adjustment of local stiffness changes the distribution of structural constraints and flexibility regions, and together with the geometry of the air cavity, it affects the target deformation.

<a id="section-双层协同设计"></a>

### 1.2 Double-layer collaborative design

The dual-layer collaborative design includes two types of structural areas: sealed walls and exoskeletons. The definitions of the mesh, materials, and design variables are as follows:



| level/rank | Grid type | Materials | Functions/Features | Design Variables |
|------|---------|------|------|---------|
| cavity | (cavities) | — | Air pressure-driven | — |
| Sealing wall | C3D6 wedge-shaped units (inside CPGEO) | Uniformly soft material | Withstand air pressure, maintain sealing, and transfer loads properly. | Follow the CPGEO shape (no independent variables). |
| **CPGEO interface** | — | — | **C3D4/C3D6 junction** | **Cavity shape: $\mathbf{\Phi}_G$** |
| exoskeleton | C3D4 tetrahedrons (outside CPGEO region) | SIMP variable density method | Restrict deformation and scaling movements | Density field: $\mathbf{\Phi}_M$ |

<a id="section-数值问题与处理方法"></a>

### 1.3 Numerical problems and solutions

| challenge | Solutions | Code location |
|------|---------|---------|
| The thin sealing layer requires precise simulation. | **Offset shell units**: CPGEO surface + normal offset → C3D6 wedge elements | `codesign/offset_boundary_part.py` |
| The exoskeleton requires extensive topological optimization. | **SIMP + BSP field parameterization**  +  **RAMP penalty interpolation** | `simp/simpmaterial.py` |
| The zero-energy mode in low-density regions leads to numerical instability. | **Fskew regularization**: Penalty for the second-order gradient antisymmetric components + adaptive penalties based on Gaussian points | `simpmaterial.py` |
| The shell structure may undergo self-crossing or distortion during optimization processes. | **Concave curvature constraint**  +  **Minimum distance constraint for the offset plane** | `codesign/constraints.py` |

<a id="section-问题形式化"></a>

### 1.4 The problem is formalized into a mathematical problem.

The joint optimization objective is to optimize the deformation response of the system based on the geometry of the air cavity $\mathbf{\Phi}_G$ and the material density field $\mathbf{\Phi}_M$, while also satisfying the equilibrium equations and manufacturability constraints. The objective function $\mathcal{J}$ can be defined flexibly according to the specific task, for example:

- **Displacement drive**: Maximizing or adjusting the displacement/rotation at the specified point.
- **Stiffness-driven**: By adjusting the **Tangent stiffness matrix** (Jacobian) of the system's equilibrium state, the flexibility or load-bearing capacity in a specific direction can be controlled.
- **Energy-driven**: The strain energy released under maximum air pressure driving conditions (work done)
- **Multi-objective combination**: The weighted sum of the above targets

The general form is:

$$
\min_{\mathbf{\Phi}_G, \mathbf{\Phi}_M} \mathcal{J}\bigl(\mathbf{u}(\mathbf{\Phi}_G,\mathbf{\Phi}_M),\; \mathbf{K}_T(\mathbf{\Phi}_G,\mathbf{\Phi}_M)\bigr), \quad \text{s.t.} \quad \mathbf{R}(\mathbf{u}, \mathbf{\Phi}_G, \mathbf{\Phi}_M) = \mathbf{0}
$$

Among them, $\mathbf{u}$ represents the displacement field, $\mathbf{K}_T = \partial\mathbf{R}/\partial\mathbf{u}$ represents the tangent stiffness matrix (Jacobian), and $\mathbf{R} = \mathbf{0}$ represents the static equilibrium equations.

---

<a id="section-几何建模可变形气腔与偏置壁面"></a>

## 2 Geometric modeling: deformable air cavities and offset walls

<a id="section-整体架构"></a>

### 2.1 Overall architecture

The CPGEO spherical mapping closed surface defines the **The interface between the C3D4 solid domain and the C3D6 sealing wall** region. The sealing wall is generated by the CPGEO surface along the **Normal direction is biased inward** direction, with thin-walled air cavities constructed using C3D6 wedge elements stacked together. The outer part of the CPGEO surface is filled with C3D4 tetrahedral meshes, which are used for the topological optimization of SIMP exoskeletons.

```
A complete finite element model (from inside to outside) =
  Cavities/hollows
  + C3D6 Cuneated unit layers (with biased shell walls, uniform soft materials used to ensure sealing)
  + CPGEO interface ← Control point $\mathbf{\Phi}_G$ defines the shape of this interface.
  + C3D4 Tetrahedral mesh (solid domain, SIMP variable density exoskeleton)
```

<a id="section-壳单元构建流程"></a>

### 2.2 Shell component construction process

The construction of the offset shell starts from the CPGEO interface, and extends towards **Gas cavity side (normal direction opposite)** to create a sealing wall.

1. **Base layer extraction**: Use the grid nodes on the CPGEO interface as the base layer (layer 0) of the sealing wall.
2. **Stacking offset**: For each layer $l = 1, \dots, N_{\text{layer}}$, generate new nodes by shifting inward along the normal direction.
   $$
   \mathbf{x}^{(l)}_i = \mathbf{x}^{(0)}_i - \frac{l}{N_{\text{layer}}} \cdot t \cdot \mathbf{n}_i
   $$
   Among them, $t$ represents the total thickness of the sealing wall, and $\mathbf{n}_i$ represents the unit normal vector at the base node (pointing towards the C3D4 side).
3. **Constructing wedge-shaped units**: Connect nodes between adjacent layers to generate C3D6 wedge elements. Create an offset surface at the innermost layer for pneumatic loading.

<a id="section-法向量计算"></a>

### 2.3 Calculation of the normal vector

The normal vector can be determined by calculating the cross product of the tangent vectors of the CPGEO surface parameterized by $\mathbf{r}(u,v)$:

$$
\mathbf{n} = \frac{\partial \mathbf{r}}{\partial u} \times \frac{\partial \mathbf{r}}{\partial v}
$$

Both grid generation and sensitivity analysis utilize the same set of normal vectors, which ensures the continuity of shape sensitivity characteristics.

<a id="section-装配体修改计算图保持"></a>

### 2.4 Assembly modification (computational graph preservation)

Each time the sensitivity is evaluated, it is necessary to propagate the gradient of the target shell layer nodes coordinates to the CPGEO control points. For this purpose, before the gradient calculation, **Calculating the coordinates of the reconstructed bias nodes**:

$$
\mathbf{x}^{(l)}_i(\mathbf{\Phi}_G) = \mathbf{x}^{(0)}_i(\mathbf{\Phi}_G) - \alpha_l \cdot t \cdot \mathbf{n}_i(\mathbf{\Phi}_G)
$$

The negative sign indicates an offset towards the air cavity side (normal direction). The entire chain (CPGEO control point $\to$, interface node $\to$, normal vector $\to$, offset node) is maintained in connection through automatic differentiation, ensuring that the subsequent adjoint methods can correctly transmit gradients. For details, see §8.1.

<a id="section-负高斯权重检测"></a>

### 2.5 Negative Gaussian weight detection

The offset shell element may experience geometric distortion, resulting in negative Gaussian weights. In such cases, the program will report an error and prompt users to check the quality of the mesh.

---

<a id="section-外骨骼材料设计simp-拓扑优化"></a>

## 3 Exoskeleton material design: SIMP topology optimization

<a id="section-b-样条材料场参数化"></a>

### 3.1 Parametric modeling of B-spline material fields

The material density field uses B-spline fields (BSP) for parameterization, and the same underlying technology is used for geometric parameterization. The control point $\mathbf{\Phi}_M$ is mapped to any spatial point using B-spline basis functions, resulting in **Design field values** $\chi(\mathbf{x})$:

$$
\chi(\mathbf{x}) = \sum_{i,j,k} N_i(x) N_j(y) N_k(z) \cdot (\mathbf{\Phi}_M)_{ijk}
$$

Among them, $N_i, N_j, N_k$ are B-spline basis functions in three directions. The value range of $\chi$ is unrestricted ( $-\infty < \chi < \infty$ ), and it needs to be transformed into physical density through subsequent mapping.

<a id="section-设计场到密度的映射"></a>

### 3.2 Mapping from the design field to the density

The design field value $\chi(\mathbf{x})$ is first mapped to $(0, 1)$ using the Sigmoid function:

$$
\rho_{\text{raw}}(\mathbf{x}) = \frac{1}{1 + e^{-\chi(\mathbf{x})}}
$$

After being penalized by **RAMP（Rational Approximation of Material Properties）**, the effective density ratio becomes:

$$
\rho_{\text{eff}} = \frac{\rho_{\text{raw}}}{1 + p (1 - \rho_{\text{raw}})}, \quad p = 8
$$

The advantage of RAMP over the traditional power-law SIMP is that it has a larger gradient at $\rho_{\text{raw}} \to 0$, which can more effectively suppress intermediate densities.

The final material modulus is:

$$
\mu(\mathbf{x}) = \rho_{\text{eff}} \cdot (\mu_{\max} - \mu_{\min}) + \mu_{\min}
$$

$$
\kappa(\mathbf{x}) = \rho_{\text{eff}} \cdot (\kappa_{\max} - \kappa_{\min}) + \kappa_{\min}
$$

Among them, $\mu_{\min} = \mu_{\max} \cdot \text{simp\_ratio\_min}$ needs to have its values adjusted to prevent numerical anomalies.

<a id="section-计算图完整性空间导数代理"></a>

### 3.3 Computing graph integrity: spatial derivative proxy

The SIMP density field is obtained by querying the BSP field to obtain the design field value: $\chi(\mathbf{x}_g) = \sum N(\mathbf{x}_g) \cdot \mathbf{\Phi}_M$. Here, $\mathbf{x}_g$ represents the coordinates of the Gaussian points. After applying Sigmoid and RAMP mappings, the effective density $\rho(\chi)$ is obtained. When the geometry of the air cavity $\mathbf{\Phi}_G$ changes, the grid nodes near the interface also move, causing the corresponding Gaussian point positions $\mathbf{x}_g(\mathbf{\Phi}_G)$ to change as well. This means that the design field value $\chi$ actually depends on two types of design variables simultaneously:

$$
\chi\bigl(\mathbf{x}_g(\mathbf{\Phi}_G),\; \mathbf{\Phi}_M\bigr)
$$

However, in the standard BSP field query, $\mathbf{x}_g$ is considered a constant (only $\mathbf{\Phi}_M$ is involved in the calculation graph). The path $\partial\chi/\partial\mathbf{\Phi}_G$ is truncated, resulting in the sensitivity **Incomplete**—the impact of geometric changes on the material field—being overlooked in the automatic differentiation results.

Density interpolation uses **First-order spatial derivative approximation** to approximate this gradient path using a Taylor expansion.

$$
\Delta\chi \approx \frac{\partial\chi}{\partial\mathbf{x}} \cdot \Delta\mathbf{x}(\mathbf{\Phi}_G)
$$

Among them, $\partial\chi/\partial\mathbf{x}$ is derived from the analytical derivatives of the BSP field in space, while $\Delta\mathbf{x}$ is caused by changes in the geometric control points. The correction terms remain connected in the computational graph, ensuring that the sensitivity of $\chi$ (and thus $\rho$) to $\mathbf{\Phi}_G$ is correctly inverted, thereby ensuring the integrity of the sensitivity results obtained using the adjoint method.

<a id="section-材料分配流程"></a>

### 3.4 Material distribution process

Before each finite element analysis, the standard C3D4 elements are replaced with custom elements that incorporate regularization techniques. The density field is retrieved based on the positions of Gaussian points, and each integration point is assigned independent material properties $\mu(\mathbf{x}), \kappa(\mathbf{x})$ and penalty factors $p(\mathbf{x})$ (see §4.2). The shell element (C3D6) is assigned uniform soft material parameters. For detailed implementation, see §8.2.

---

<a id="section-正则化方法抑制低密度区零能模式"></a>

## 4 Regularization methods: Suppressing zero-energy modes in low-density regions

<a id="section-问题动机"></a>

### 4.1 Problematic motives

In SIMP topology optimization, the elements in the low-density regions ($\rho \to 0$) have extremely low stiffness, making them prone to **Zero Energy Mode** (hourglass mode) – that is, the elements deform without generating strain energy. This can lead to:
- The stiffness matrix is singular or ill-conditioned.
- Non-physical sawtooth oscillations occur in the displacement field
- Sensitivity information is distorted, making optimization convergence difficult.

To suppress such patterns, MorphOpt provides three regularization strategies, all of which achieve their effect by penalizing the second-order gradient of displacement, and use **Each Gaussian point has its own independent adaptive penalty coefficient.**.

<a id="section-自适应惩罚因子"></a>

### 4.2 Adaptive punishment factor

Penalty factor $p(\mathbf{x})$ Controls the intensity of the regularization energy at each Gaussian point. This parameter is determined by the design of the field. $\chi$ The smooth mapping is calculated point by point. The transition regions are defined as follows: $\chi$ the **Negative semi-axis** ( $\chi_{\min}=-6,\;\chi_{\max}=-5$ ), to ensure that the punishment is only applied to areas where the material is weak:

$$
p(\mathbf{x}) = p_0 \cdot S\!\left(\frac{\chi_{\max} - \chi(\mathbf{x})}{\chi_{\max} - \chi_{\min}}\right), \quad S(\xi) = 6\xi^5 - 15\xi^4 + 10\xi^3
$$

Among them, $S$ represents the Smoothstep function (continuous at $\mathcal{C}^1$), and $p_0$ represents the reference penalty coefficient. This design is based on physical intuition:
- **Physical area** ( $\chi \gg 0$, $\rho \to 1$ ): The material has high stiffness, so the zero-energy mode is not likely to occur → $p \approx 0$
- **Weak material region** ( $\chi \approx -5 \sim -6$, $\rho \ll 1$ ): Extremely low stiffness, high risk in zero-energy mode → $p$ smoothly transitions from $0$ to $p_0$
- **Void area** ( $\chi \ll -6$, $\rho \to 0$ ): Full punishment → $p \approx p_0$

---

<a id="section-fskew-正则化"></a>

### 4.3 Fskew regularization

<a id="section-原理"></a>

#### 4.3.1 Principle

Fskew regularization penalty with two-step sensitivity **antisymmetric components**. The zero-energy mode is typically accompanied by high-frequency spatial oscillations in the displacement field. This regularization term characterizes the corresponding oscillations through antisymmetric second-order gradients, while retaining the symmetric components in physical deformations (such as bending strain gradients).

Define the second-order gradient tensor of displacement:

$$
U_{,ijk} = \frac{\partial^2 u_i}{\partial x_j \partial x_k}
$$

Its antisymmetric components regarding the last two indicators $j, k$ are as follows:

$$
F^{\text{skew}}_{ijk} = U_{,ijk} - U_{,ikj}
$$

The regularization energy is:

$$
E_{\text{reg}} = \int_{\Omega} p(\mathbf{x}) \; F^{\text{skew}}_{ijk} F^{\text{skew}}_{ijk} \,\mathrm{d}\Omega
$$

Among them, $p(\mathbf{x})$ represents the spatial variation penalty coefficients for each Gaussian point (§3.4). The penalty coefficients increase automatically in low-density areas and reset to zero in high-density areas.

In implementation, the regularized energy is superimposed on the hyperelastic strain energy in the element `potential_Energy()`. At the same time, `_get_EpdUe_EpdUe2()` provides corrections for the internal forces (first-order variation) and tangent stiffness (second-order variation). For the specific code, see §8.3.

<a id="section-fgrad-正则化备选"></a>

### 4.4 Fgrad regularization (alternative method)

Directly penalize the displacement with a two-step mechanism for **Complete Frobenius norm** (rather than only dealing with the antisymmetric part):

$$
E_{\text{reg}}^{\text{Fgrad}} = \int_{\Omega} p(\mathbf{x}) \; U_{,ijk} U_{,ijk} \,\mathrm{d}\Omega
$$

This method also penalizes the linear strain gradient in bending deformation, and its invasiveness towards physical deformation is slightly higher than that of Fskew.

<a id="section-huhu_lulu-正则化试验性"></a>

### 4.5 HuHu_LuLu regularization (experimental approach)

`SIMPElementHuHu_LuLu` only penalizes the second-order sensitivity of displacement, which is equivalent to retaining the partial quantities to minimize the interference with physical bending: **Traces (volume components)**

$$
E_{\text{reg}}^{\text{dev}} = \frac{1}{2} \int_{\Omega} p(\mathbf{x}) \left[ \sum_{i,j,k} (U_{,ijk})^2 - \frac{1}{3} \sum_{i,j} \Bigl( \sum_{k} U_{,ijk} \Bigr)^2 \right] \mathrm{d}\Omega
$$

Its physical meaning is similar to the decomposition of strain into volume and lateral components in elasticity mechanics. The zero-energy mode is mainly characterized by volume distortion (lateral components dominate), therefore, targeting the lateral components, the Fskew method remains the most efficient choice.

---

<a id="section-单元组合与默认选择"></a>

### 4.6 Unit combination and default selection

The default element combination is `C3D10 + Fskew`. Details of each option and its applicable scenarios can be found in the code implementation and table in §8.3. All regularization methods support independent penalty factors for each Gaussian point (§4.2).

---

<a id="section-形状-材料联合优化模型"></a>

## 5 Shape-material combined optimization model

<a id="section-设计变量"></a>

### 5.1 Design Variables

The design variables in joint optimization problems fall into two categories:

| Category | symbols | Description | dimension | updater |
|-----|------|------|------|--------|
| Air cavity control points | $\mathbf{\Phi}_G$ | Control point coordinates of the spherical mapping CPGEO | $\mathbb{R}^{N_G \times 3}$ | `UpdaterBoundaryPart` |
| Material density field control points | $\mathbf{\Phi}_M$ | BSP Field Control Points (Density Values) | $\mathbb{R}^{N_M}$ | `UpdaterSIMPMaterial` |

<a id="section-目标函数"></a>

### 5.2 objective function

The typical objective function is to maximize structural stiffness (minimize total potential energy) or maximize work done (such as releasing energy due to torsion). It can include weighted considerations for multiple load cases:

$$
\mathcal{J} = \sum_{s=1}^{N_s} w_s \cdot \Pi_s(\mathbf{u}_s, \mathbf{\Phi}_G, \mathbf{\Phi}_M)
$$

The volume fraction $\bar\rho = \frac{\int_\Omega \rho(\mathbf{x}) \, \mathrm{d}\Omega}{\int_\Omega \mathrm{d}\Omega}$ can be incorporated into the objective as a constraint or penalty term.

<a id="section-联合更新策略"></a>

### 5.3 Combined update strategy

In each optimization step, two types of design variables **Share the same set of finite element analysis results** are considered, but each is subjected to its own sub-optimization. The overall gradient $\nabla_{\mathbf{\Phi}}\mathcal{J}$ is calculated in one go using the adjoint method, and then the results are derived using the variable search method.

$$
\nabla_{\mathbf{\Phi}_G}\mathcal{J} \longrightarrow \text{UpdaterBoundaryPart} \quad \text{(L-BFGS + geometric constraints)}
$$
$$
\nabla_{\mathbf{\Phi}_M}\mathcal{J} \longrightarrow \text{UpdaterSIMPMaterial} \quad \text{(L-BFGS + material constraints)}
$$

The two sub-optimizations continue to update their respective design variables alternately or concurrently, thereby moving on to the next iteration.

---

<a id="section-协同约束"></a>

## 6 Coordination constraints

Collaborative optimization requires addressing two types of geometric constraints to ensure the manufacturability and numerical stability of the shell structure.

<a id="section-内凹曲率约束inwardcurvatureradius"></a>

### 6.1 Inward Curvature Constraint (InwardCurvatureRadius)

The offset shell is obtained by offsetting the air cavity surface along the normal direction. If the **Inner concavity curvature** of the air cavity surface is too large, the offset surface will intersect itself, resulting in grid distortion.

Constraints are defined as follows:

$$
k_{\text{inward}} \leq \frac{1}{t_{\text{eff}}}, \quad t_{\text{eff}} = t + m_{\text{ratio}} \cdot t + m_{\text{abs}}
$$

Among them, $k_{\text{inward}} = \max(k_1^+, k_2^+)$ represents the positive principal curvatures (only in the concave direction), and $t$ represents the shell thickness. The principal curvatures are obtained by solving the eigenvalues of the shape operator using the first and second fundamental forms of the surface.


<a id="section-偏移面最小距离约束offsetsurfaceminthickness"></a>

### 6.2 OffsetSurfaceMinThickness constraint

The outer surface of the offset shell may collide with itself during the deformation process. This constraint creates a neighborhood graph on the offset surface, ensuring that the distance between adjacent elements is not less than the minimum thickness.

During initialization, neighbors on the offset surface are searched using the KD-Tree; each time the method is called, the minimum distance is dynamically adjusted based on the normal angle, and a penalization is applied using an exponentially enhanced obstacle function.

$$
\mathcal{L}_{\text{dist}} = \sum_{(i,j) \in \mathcal{N}} \text{penalty}\bigl(d_{ij},\; d_{\min} \cdot \text{opposition}_{ij}\bigr)
$$

<a id="section-几何约束汇总"></a>

### 6.3 Summary of Geometric Constraints

The constraint system in MorphOpt CodeDesign:

| constraint | Class name | Function/Role | Corresponding papers |
|-----|------|------|---------|
| Inner concavity curvature | `InwardCurvatureRadius` | The concave curvature within the air cavity must be ≤ 1/thickness. | TRO2023 §IV-B |
| Distance between the offset plane | `OffsetSurfaceMinThickness` | Prevent the outer surface from intersecting itself repeatedly. | Newly added |
| The surfaces are smoothly rounded | `Fairness` | Tangential angle + uniformity of tangential vectors | TRO2023 §IV-C |
| Distance between surfaces | `Distance` | Minimum distance between surfaces | TRO2023 §IV-A |
| Designing domain boundaries | `Cylinder` / `MinRadius` | Constraints are defined within the design domain. | TRO2023 §IV |
| Material density range | `MinValue` / `MaxValue` | $\rho \in [0.001, 0.999]$ | SIMP standard |

---

# Part II – Implementation Details

---

<a id="section-代码架构总览"></a>

## 7 Overview of Code Architecture

<a id="section-文件组织"></a>

### 7.1 File organization

```
morphopt/
├── codesign/
│   ├── __init__.py
│   ├── offset_boundary_part.py ← Offset shell construction, normal vector, modify_assembly
│   ├── update_offset_boundary_part.py ← Bias PartUpdater
│   └── constraints.py     ← InwardCurvatureRadius / OffsetSurfaceMinThickness
├── optcore/
│   ├── modelparams/materials/
│   │   ├── base_material.py
│   │   ├── homogeneous_material.py
│   │   └── models.py
│   ├── modelparams/materialsparams.py ← MaterialsParams Aggregation
│   ├── updaters/materials/
│   │   └── objectivefuncs/  ← Sensitivity、DensityFieldMinimize
│   └── solver.py           ← Sensitivity analysis using the adjoint method
├── simp/
│   └── simpmaterial.py     ← SIMP_BSPFieldMaterials、SIMPElementFskew/Fgrad/...
└── task_scripts/          ← Collaborative Design Task Script Directory (Example)
```

<a id="section-类继承链"></a>

### 7.2 Inheritance chain

```
MaterialsParams                 ← Aggregate multiple material interfaces and combine design variables together.
  ├── SIMP_BSPFieldMaterials    ← C3D4/C3D8 SIMP density field
  └── HomogeneousMaterial        ← C3D6 Uniform materials for shell and other components

torchfea.elements.Element_3D
  ├── SIMPElementFskew          ← Fskew Regularization
  ├── SIMPElementFgrad          ← Fgrad Regularization (alternative method)
  ├── SIMPElementHuHu_LuLu      ← Volume component regularization (experimental)
  └── SIMPElementC3D10          ← C3D10 + Fskew Inheritance combination (default)
         (C3D10, SIMPElementFskew)
```

<a id="section-数据流示意"></a>

### 7.3 Schematic diagram of data flow

```
Φ_G (CPGEO cps) ──→ modify_assembly() ──→ Shell node coordinates
Φ_M (BSP cps)   ──→ set_materials()   ──→ μ(χ), κ(χ), p(χ)  @ Gauss point
                                         └─→ Replace with SIMPElementC3D10
FEA Solve it─→ Objective function ──→ Accompanying verbs ──→ dJ/dΦ_G + dJ/dΦ_M
                                        ├──→ UpdaterOffsetBoundaryPart
                                        └──→ UpdaterSIMPMaterial
```

---

<a id="section-关键实现细节"></a>

## 8 Key implementation details

<a id="section-几何偏置壳构建与计算图保持"></a>

### 8.1 Geometry: Construction of offset shells and maintenance of computational graphs

<a id="section-壳网格生成codesignoffset_boundary_partpy"></a>

#### 8.1.1 Shell grid generation (`codesign/offset_boundary_part.py`)

`OffsetBoundaryPart._build_shell_c3d6()` is executed each time the mesh is recreated. It starts from the CPGEO interface and biases towards the air cavity side, then constructs C3D6 wedge elements (the inner cavity surface indices start from 1):

```python
def _build_shell_c3d6(self, part: torchfea.Part) -> torchfea.Part:
    # Obtaining the triangular mesh at the CPGEO interface (where C3D4/C3D6 boundaries occur).
    tri_by_surface = {}
    for sidx in range(1, int(self.num_surface_interfaces)):
        surf_name = f"surface_{sidx}_All"
        tri = part.surfaces.get_trimesh(surf_name)
        tri_by_surface[sidx] = tri

    # For each layer, nodes are generated by shifting in the normal direction (towards the air cavity side).
    for layer in range(1, self.num_layers + 1):
        alpha = float(layer) / float(self.num_layers)
        new_xyz = base_nodes + alpha * disp
        nodes_all = torch.cat([nodes_all, new_xyz], dim=0)

    # Construct C3D6 wedge-shaped units to form connections between them.
    wedge6 = np.stack([n0, n1, n2, n3, n4, n5], axis=1)
    part.add_element(element, name="C3D6")

    # Create an offset surface (used for air pressure loading).
    part.add_surface_set(surf_name_offset, [(elem_ids, 1)])
```

<a id="section-解析法向量"></a>

#### 8.1.2 Determining the normal vector

For the surface `get_normals()` of CPGEO, the parametric normal vector pointing towards the C3D4 side (outer side) is directly returned (the surface is taken from the Part interface `surface_interfaces()`):

```python
def _compute_normals(self, base_nodes):
    normal_list = []
    for sfidx in range(1, self.num_surface_interfaces):
        normals = self.surface_interfaces()[sfidx].get_normals(surf_node_uv)
        normal_list.append(normals)
    return torch.cat(normal_list, dim=0)
```

<a id="section-计算图保持"></a>

#### 8.1.3 Computational graph persistence

Each time the sensitivity is evaluated, the calculation graph of the `modify_assembly()` reconstruction bias node coordinates is generated, enabling autograd to propagate backward to the control points.

```python
def modify_assembly(self, design_sensitivity_vars, assembly):
    super().modify_assembly(design_sensitivity_vars, assembly)
    
    # Current Control Point → Surface Node → Normal Offset Target → Shell Node
    # The entire chain remains connected through autograd.
    base_nodes = nodes[base_ids]
    target_nodes = self._compute_offset_targets(base_nodes)
    disp = target_nodes - base_nodes

    # Update nodes at all levels (the computation graph remains intact, used for subsequent sensitivity analysis).
    for layer in range(1, self.num_layers + 1):
        alpha = float(layer) / float(self.num_layers)
        nodes[layer_ids] = base_nodes + alpha * disp
```

<a id="section-偏置层网格检查"></a>

#### 8.1.4 Bias layer grid inspection

```python
weights = shell.gaussian_weight
if not torch.isfinite(weights).all() or (weights <= 0).any():
    raise ValueError("Invalid offset shell mesh.")
```

---

<a id="section-材料bsp-场--ramp--自适应惩罚"></a>

### 8.2 Materials needed: BSP field + RAMP + adaptive punishment mechanisms

<a id="section-bsp-场初始化"></a>

#### 8.2.1 BSP field initialization

```python
# Initialize the BSP field.
basis_x = bspmap.BasisClamped(num_cps=nx, degree=degree)
basis_y = bspmap.BasisClamped(num_cps=ny, degree=degree)
basis_z = bspmap.BasisClamped(num_cps=nz, degree=degree)

bsp = bspmap.BSP(basis=[basis_x, basis_y, basis_z], control_points=control_points)
self.simp_field = bsp
self._cps = torch.from_numpy(bsp.control_points)  # Design Variables
```

<a id="section-ramp-密度插值"></a>

#### 8.2.2 RAMP density interpolation

```python
def get_material_ratio(self, designfield):
    rho = 1 / (1 + torch.exp(-designfield))          # Sigmoid → (0, 1)
    rho_penalty = RAMP_interpolation(rho, p=8)       # RAMP penalties
    ratio = rho_penalty * (1 - self._simp_ratio_min) + self._simp_ratio_min
    return ratio

def RAMP_interpolation(rho, p):
    return rho / (1 + p * (1 - rho))
```

<a id="section-空间导数代理计算图补全"></a>

#### 8.2.3 Spatial derivative proxy (for computing graph completion)

The position of the Gaussian points changes with the geometric control points $\mathbf{\Phi}_G$, but the standard BSP query treats them as constants, cutting off the gradient path from $\chi$ to $\mathbf{\Phi}_G$. This correction restores the missing dependence through a first-order Taylor expansion.

```python
def get_ratio_with_spatial_derivative(self, nodes):
    # Calculate the field values and their spatial gradients.
    rdx = (wdx * cps).sum(dim=-1)   # ∂χ/∂x
    rdy = (wdy * cps).sum(dim=-1)   # ∂χ/∂y
    rdz = (wdz * cps).sum(dim=-1)   # ∂χ/∂z
    
    # Construction of spatial proxy correction: Δχ ≈ ∇χ · Δx
    # The value of the surrogate factor is used in the forward calculation, but its gradient is blocked due to the use of “detach” mechanism.
    # Only the gradient path of the result, with respect to the position change Δx, is retained.
    surrogate = rdx * x + rdy * y + rdz * z
    result = result + (surrogate - surrogate.detach())
    return result
```

The expression `result + (surrogate - surrogate.detach())` retains the forward calculation results, while also preserving the Gaussian point coordinates up to the gradient path at $\chi$. This path corresponds to the contribution transmitted through the material field in $\partial\mathcal{J}/\partial\mathbf{\Phi}_G$.

<a id="section-自适应惩罚因子-1"></a>

#### 8.2.4 Adaptive punishment factor

```python
def get_penalty_factor(self, designfield):
    influence_max = -5          # χ ≥ -5 → Entity region, p ≈ 0
    influence_min = -6          # χ ≤ -6 → void area; p ≈ p₀

    normalized = (influence_max - designfield) / (influence_max - influence_min)
    normalized = torch.clamp(normalized, 0.0, 1.0)

    # Smoothstep: C¹ is continuous, with a smooth transition from 0 to 1 within the interval from -6 to -5.
    penalty_factor = 6 * normalized**5 - 15 * normalized**4 + 10 * normalized**3
    return penalty_factor
```

<a id="section-材料装配"></a>

#### 8.2.5 Material assembly

```python
def set_materials(self, fe):
    # Replace unit type (includes Fskew regularization)
    elements_new = self.SIMPElementC3D10(elems_index=elements._elems_index,
                                          elems=elements._elems,
                                          penalfactor=self.voidpenalfactor)
    
    # Querying the density at the Gaussian integration point
    designfield = self._map_bsp_designfield(gaussian_points_locations)
    ratio_now = self.get_material_ratio(designfield)
    
    # Apply SIMP spatial scaling to the TorchFEA constitutive model selected for the current interface.
    materials = SIMPScaledMaterial(self.create_material(), ratio_now)
    elements_new.set_materials(materials)
    
    # Each Gaussian point has a separate penalty factor.
    elements_new.penalfactor = self.get_penalty_factor(designfield) * self.voidpenalfactor
```

<a id="section-壳材料处理独立材料接口"></a>

#### 8.2.6 Shell material processing (independent material interfaces)

```python
class MaterialsParams(morphopt.MaterialsParams):
    def define_interface(self):
        self.add_interface(
            morphopt.SIMP_BSPFieldMaterials(
                material_parameters=self.materialmodels.NeoHookeanLnJParams(
                    mu=4.5, kappa=45.0),
                mumax=4.5, kappamax=45.0, simp_ratio_min=1e-4,
                bounding_box=[-10, 10, -10, 10, 0, 100],
                simp_field_resolution=1.0, degree=3,
                part_name="body", elementname="C3D4"),
            name="solid")
        self.add_interface(
            self.HomogeneousMaterial(
                material_parameters=self.materialmodels.NeoHookeanLnJParams(
                    mu=0.48, kappa=4.8),
                density=1.08e-9,
                part_name="body", elementname="C3D6"),
            name="shell")
```

---

<a id="section-正则化fskew--fgrad--huhu_lulu-单元实现"></a>

### 8.3 Regularization: Implemented using Fskew / Fgrad / HuHu_LuLu units.

<a id="section-fskew-正则化实现"></a>

#### 8.3.1 Implementation of Fskew regularization

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
                    # +4 items: δ_{IJ}δ_{ik}δ_{jl}
                    I, i, j, J, k, l = I0, i0, j0, I0, i0, j0
                    self._EmdUe_2[:, I, :, J, :] += \
                        torch.einsum('gea,geb->abe',
                            self._dN2WP[:, :, i, j, :],
                            self.shape_function_d2_gaussian[:, :, k, l, :]) * 4
                    # -4 items: δ_{Ii}δ_{Jk}δ_{jl}
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

        Ugrad2 = sum(shape_func_d2[i] * U[elems[:, i]]
                     for i in range(self.num_nodes_per_elem))
        EmdUgrad2 = 4 * (Ugrad2 - Ugrad2.transpose(2, 3))
        EmdUe = torch.einsum('gIij,geija->aIe', EmdUgrad2, self._dN2WP)

        if if_onlyforce:
            return EmdUe + result0
        return EmdUe + result0[0], self._EmdUe_2 + result0[1]
```

<a id="section-默认单元组合"></a>

#### 8.3.2 Default unit combination

```python
class SIMPElementC3D10(torchfea.elements.C3D10, SIMPElementFskew):
    pass
```

---

<a id="section-灵敏度分析与自动微分"></a>

### 8.4 Sensitivity analysis and automatic differentiation

<a id="section-设计变量到装配体的映射"></a>

#### 8.4.1 The mapping from design variables to the final assembly.

```python
# Geometric control points → Modify node coordinates
geometry.modify_assembly(dv['geometry'], assembly)

# Material Density Control Points → Modify the properties of Gaussian-point materials.
materials.modify_assembly(dv['materials'], assembly)
```

<a id="section-联合灵敏度求解"></a>

#### 8.4.2 Joint sensitivity solution

After solving the FEA problem once, the gradient of the objective function with respect to all design variables can be obtained using the adjoint method.

```python
design_gradients = solver.get_jacobian_sensitivity_multistep(
    fe_results=self.fe_results,
    design_vars=torch.cat([Φ_G, Φ_M], dim=0),
    load_names=self.jacobian_needed,
    apply_func=apply_func,
    compute_objective_funcs=obj,
)
```

<a id="section-梯度分配"></a>

#### 8.4.3 Gradient distribution

```python
grad_G = design_gradients[:len(Φ_G)]  # → UpdaterBoundaryPart
grad_M = design_gradients[len(Φ_G):]  # → UpdaterSIMPMaterial
```

<a id="section-材料灵敏度平滑"></a>

#### 8.4.4 Material sensitivity smoothing

The `Sensitivity` class uses gradients as a linear proxy objective for material sub-optimization:

```python
class Sensitivity(BaseObjective):
    def __call__(self, cps, *args, **kwargs):
        return ((cps - self._cp0) * self.sensitivity).sum()
```

`DensityFieldMinimize` provides slight regularization terms, causing the density field to approach zero.

```python
class DensityFieldMinimize(BaseObjective):
    def __call__(self, cps, *args, **kwargs):
        return self.scale * (cps.sum() + 1)**2
```

---

<a id="section-数值流程"></a>

## 9 Numerical processes

<a id="section-完整优化循环"></a>

### 9.1 Complete optimization of the loop

```
Algorithm: Co-Design and collaborative optimization
———————————————————————————————————
while Not converged:
    # ---- Grid generation ----
    1. Spherical Mapping Cavity (CPGEO)← Φ_G
    2. Generating C3D4 tetrahedral mesh (solid domain)
    3. Offset shell construction (C3D6)← Air cavity surface area + thickness
    4. Create an offset surface (air pressure loading surface).
    
    # ---- Material allocation ——
    5. BSP Design the field φ(x). ← Φ_M
    6. Sigmoid → RAMP(p=8) Penalty interpolation: μ(φ), κ(φ)
    7. Smoothstep Mapping → Gaussian-point penalty factor p(φ)
    8. Shell units are evenly distributed with materials throughout.
    
    # ---- FEA ----
    9. Newton-Raphson Solving for static equilibrium
    
    # ---- Sensitivity ———
    10. Objective function calculation
    11. Automatic differentiation + adjoint method → dJ/dΦ_G, dJ/dΦ_M
    
    # ---- Geometric sub-optimization (UpdaterBoundaryPart) ----
    12. Shape derivative proxy target + geometric constraint terms
    13. L-BFGS subproblem ← dJ/dΦ_G
    14. Updating Φ_G (air cavity control points)
    
    # ---- Material Sub-Optimization (UpdaterSIMPMaterial) ----
    15. Material sensitivity proxy target + density range constraints
    16. L-BFGS subproblem ← dJ/dΦ_M
    17. Updating Φ_M (density field control points)
    
    # ---- Surface reconstruction ——
    18. If the reconstruction interval is reached, perform spherical mapping reconstruction.
    
    # ---- Save ----
    19. Save history, visualize data.
———————————————————————————————————
```

<a id="section-代码架构对应"></a>

### 9.2 Code architecture correspondence

```
Controller                         → Optimizing the main loop (optcore/controller.py)
├── Params                         → Parameter combination (optcore/modelparams/params.py)
│   ├── Geometry (OffsetBoundaryPart) → Air cavity CPGEO + offset shell (codesign/offset_boundary_part.py)
│   │   └── _build_shell_c3d6()    → C3D6 Shell generation
│   │   └── modify_assembly()      → Update node coordinates.
│   ├── FEAParams (FEAParams) → FEA Parameters (optcore/modelparams/feaparams.py)
│   │   └── create_fea()           → General-purpose loads and constraints assembly
│   └── MaterialsParams → solid SIMP + shell HomogeneousMaterial interfaces
│       ├── SIMPElementC3D10       → C3D10 + Fskew Regularization
│       ├── get_material_ratio()    → Sigmoid + RAMP(p=8) Density interpolation
│       ├── get_penalty_factor()    → Smoothstep Gaussian point penalty coefficient
│       └── set_materials()         → assign μ(φ), κ(φ) + penalty factor
├── Solver                    → FEA Solve the problem using optcore/solver.py.
├── ObjectiveFunction              → Objective function (defined by the example)
└── Updaters                       → Design variable update (optcore/updaters/updaters.py)
    ├── UpdaterOffsetBoundaryPart    → Geometric suboptimization
    │   ├── ShapeDerivative         → Shape sensitivity proxy
    │   ├── Fairness / Distance    → Geometric constraints
    │   ├── InwardCurvatureRadius   → Concave curvature constraints (codesign/constraints.py)
    │   ├── OffsetSurfaceMinThickness → Offset plane distance constraints (codesign/constraints.py)
    │   └── Cylinder               → Boundary constraints
    └── UpdaterSIMPMaterial           → Suboptimal material optimization
        ├── Sensitivity             → Material sensitivity proxy
        ├── DensityFieldMinimize    → Density regularization
        └── MinValue / MaxValue    → Density range constraints
```

<a id="section-设计变量数量参考"></a>

### 9.3 Reference: Number of design variables

Below is the scale of variables used in the example of torsional coupling design:

| variables | quantity | Description |
|-----|------|------|
| Air cavity control points: $\mathbf{\Phi}_G$ | 477 × 3 = 1,431 | Spherical mapping CPGEO |
| Density field control point $\mathbf{\Phi}_M$ | 51 × 51 × 51 = 132,651 | 3-order BSP field |

There is a significant difference in the number of variables between the two types of load cases. Therefore, performing sub-optimizations separately allows for setting different step sizes and convergence conditions based on their respective characteristics.

---

<a id="section-完整代码示例"></a>

## 10 Complete code example

<a id="section-示例脚本结构"></a>

### 10.1 Example script structure

The following code illustrates the module definitions for collaborative optimization tasks:

```python
import morphopt
import torch
import cpgeo

# Material parameters
mumax = 4.82          # Maximum shear modulus (for hard materials)
minratio = 1e-6       # Minimum density ratio

class ThisController(morphopt.Controller):

    # ---- Objective Function ----
    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def objective_function(self):
            # The potential energy difference between the two load steps (torsional energy)
            E0 = assembly._total_Potential_Energy(RGC=RGC0)
            E1 = assembly._total_Potential_Energy(RGC=RGC1)
            return E1 - E0

    # ---- Parameter Definitions ----
    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):
            def define_interface(self):
                # A boundary condition: a cavity surface with a certain offset around it.
                body = morphopt.OffsetBoundaryPart(
                    fea_seed_size=2.5,
                    shell_thickness=2.5,   # Shell thickness: 2.5 mm
                    num_layers=1)          # Single-layer shells
                body.add_surface_interface(body.BSP.initialize_cylinder(...))
                cavity = body.CPGEO.initialize_Sphere(...)
                cavity.is_updatable = True
                body.add_surface_interface(cavity)
                self.add_interface(body, name='body')

        class FEAParams(morphopt.FEAParams):
            def define_interface(self):
                self.add_interface(self.Pressure(
                    instance_name='body',
                    surface_name='surface_1_offset'),  # Air pressure is applied to the offset surface.
                    name='pressure_1')

        class MaterialsParams(morphopt.MaterialsParams):
            def define_interface(self):
                self.add_interface(morphopt.SIMP_BSPFieldMaterials(
                    material_parameters=self.materialmodels.NeoHookeanLnJParams(
                        mu=mumax, kappa=mumax * 10),
                    mumax=mumax, kappamax=mumax * 10,
                    simp_ratio_min=minratio,
                    bounding_box=[-25, 25, -25, 25, 0, 50],
                    simp_field_resolution=1.0, degree=3,
                    voidpenalfactor=1e-1,
                    part_name="body", elementname="C3D4"),
                    name="solid")
                self.add_interface(self.HomogeneousMaterial(
                    material_parameters=self.materialmodels.NeoHookeanLnJParams(
                        mu=0.48, kappa=4.8),
                    density=1.08e-9,
                    part_name="body", elementname="C3D6"),
                    name="shell")

    # ----Updater----
    class Updater(morphopt.Updaters):
        def define_updater(self) -> None:
            # Name: Specifies the target interface. Bound to the Part with the name 'body' in the params.geometry.
            self.add_geometry_updater(self.UpdaterOffsetBoundaryPart(), name='body')
            # Find the material interface named "solid" in params.materials.
            self.add_material_updater(self.UpdaterSIMPMaterial(), name='solid')

        def __init__(self, params):
            super().__init__(params=params)

        class UpdaterOffsetBoundaryPart(morphopt.UpdaterOffsetBoundaryPart):
            def __init__(self):
                super().__init__(max_step_iter=100)   # Without a goal/objective

            def define_objective(self) -> None:
                self.add_objective_function(self.objectivefuncs.ShapeDerivative())
                # Constraints only apply to the parts bound to this editor.
                self.add_constraints(self.objectivefuncs.Fairness())
                self.add_constraints(self.objectivefuncs.Distance(min_distance=...))
                self.add_constraints(self.objectivefuncs.InwardCurvatureRadius())
                self.add_constraints(self.objectivefuncs.OffsetSurfaceMinThickness(min_distance=2.0))

        class UpdaterSIMPMaterial(morphopt.UpdaterSIMPMaterial):
            def __init__(self):
                super().__init__(max_step_iter=200, max_step_length=0.1)

            def define_objective(self) -> None:
                self.add_objective_function(Sensitivity())
                self.add_constraints(MinValue(xmin=0.001))
                self.add_constraints(MaxValue(xmax=0.999))
                self.if_update = True

if __name__ == '__main__':
    morphopt.start_optimization(device='cpu', restart_per_iteration=20)
```

<a id="section-其他-codesign-示例"></a>

### 10.2 Other examples of collaborative designs

For collaborative optimization, the following objectives can be used in the configuration process:

| Type of example cases | Objective | Characteristics |
|---------|------|------|
| Optimization of twist angle | Maximizing the torsional angle | 3-fold rotational symmetry air cavity + SIMP skeleton |
| Optimized torsion energy | Maximizing the energy released from torsion | The goal is to achieve a difference in potential energy. |
| Optimization of elongation stiffness | Maximized elongation stiffness | Unidirectional stretching |
| Optimized contraction energy | Maximizing the energy of contraction | Negative Poisson ratio effect |
| Optimization of contraction and deformation | Contraction deformation | Comparative validation |

---

<a id="section-参考文献"></a>

## 11 References

1. **Chen F, Song Z, et al.** *Morphological Design for Pneumatic Soft Actuators and Robots with Desired Deformation Behavior.* IEEE Transactions on Robotics, 2023.

2. **Song Z, Chen F, et al.** *Continuum Jacobian based Computational Morphogenesis for Soft Robotic Workspace Optimization.* IEEE Transactions on Robotics, 2025.
