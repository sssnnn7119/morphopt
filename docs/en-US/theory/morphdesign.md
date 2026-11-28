# MorphOpt optimization theory

[简体中文](../../zh-CN/theory/morphdesign.md)

> This document combines the core theories and code implementations of two papers to systematically explain the mathematical principles and numerical methods used in the shape optimization of soft robotic bodies within the MorphOpt framework.

---

## Contents

<!-- docs:toc depth=1 -->

- [1 Problem description](#section-问题概述)
- [2 Geometric representation](#section-几何表示)
- [3 Mechanical models](#section-力学模型)
- [4 Optimization problem modeling](#section-优化问题建模)
- [5 Sensitivity analysis (using the discrete adjoint method based on automatic differentiation)](#section-灵敏度分析基于自动微分的离散伴随法)
- [6 Workspace optimization and the continuum Jacobian](#section-工作空间优化与连续体雅可比矩阵)
- [7 Geometric constraints](#section-几何约束)
- [8 Design subproblems and local surrogate models](#section-子优化与信赖域方法)
- [9 Numerical processes](#section-数值流程)
- [10 References](#section-参考文献)
- [11 Discrete integration of geometric penalty terms and weights](#section-几何罚项的离散积分与权重)

<!-- /docs:toc -->

---

<a id="section-问题概述"></a>

## 1 Problem description

The deformation behavior of the pneumatic soft robot is determined by its **form/structure** (including the shape of the internal air cavity and the external contour). After a given input pressure, the flexibility of the soft material allows for continuous large deformations. The goal of the morphological design is to **Inverse solution**: to automatically determine the optimal internal and external geometric shapes, thereby achieving the desired deformation behavior.

The optimization problems solved by MorphOpt can be categorized into two types:

| Type of issue               | Description                                                                         | Corresponding papers        |
| ---------------------- | ---------------------------------------------------------------------------- | --------------- |
| **Design of deformable shapes** | Given the target deformation (elongation, bending angle, torsion angle, or spatial curve), optimize the shape to make the actual deformation close to the target value. | TRO2023Morph    |
| **Optimization of workspace** | Maximize the set of reachable positions/poses of the end effector (volume of the working space), while optimizing the shape and input air pressure  | TRO2025Jacobian |

The common technical basis for both types of problems includes:

- Freeform surface geometry parameterization (B-spline/spherical mapping)
- Nonlinear finite element analysis (hyperelastic Neo-Hookean model)
- Sensitivity analysis using the discrete adjoint method based on automatic differentiation
- A design subproblem with a local model, step bounds and a quasi-Newton solver

---

<a id="section-几何表示"></a>

## 2 Geometric representation

<a id="section-b-样条曲面外表面与气腔表面"></a>

### 2.1 Spline surfaces (outer surface and air cavity surfaces)

For surfaces that need to maintain a cylindrical shape, such as the outer surface of a robot, use **Spline surfaces** for parameterization:

$$
\mathbf{r}(q,r) = \sum_{j=1}^{m} \sum_{i=1}^{n} \mathbf{P}_{ij}\, B_i^q(q)\, B_j^r(r)
$$

Among them:

- $\mathbf{r} \in \mathbb{R}^3$ represents any point on the surface.
- $\mathbf{P}_{ij} \in \mathbb{R}^3$ represent the coordinates of the control points.
- $B_i^q, B_j^r$ represents the B-spline basis function (Cox-de Boor recurrence formula).
- $(q,r)$ represents the parametric coordinates of the surface, including both longitudinal and circumferential directions.

The B-spline has **Local supportability**: Adjustments made to a single control point affect the local surface area, and the corresponding sensitivity mapping has a sparse structure.

<a id="section-代码对应"></a>

#### 2.1.1 Code correspondence

In `src/morphopt/shapeopt/surfaces/`, `BspSurface` (alias `BSP`) implemented the initialization and operations for B-spline surfaces; the surface belongs to a certain boundary Part:

```python
class GeometryParams(morphopt.GeometryParams):
    class BoundaryPart(morphopt.BoundaryPart):
        def define_surfaces(self):
            self.add_surface_interface(
                self.BSP.initialize_cylinder(
                    r0=8., length=80., seed_size=1.0,
                    symmetric=[1, [1]],
                    perturbation_L=12.
                )
            )

    def define_interface(self):
        self.add_interface(self.BoundaryPart(fea_seed_size=1.0), name='body')
```

<a id="section-球面映射闭曲面内嵌气腔"></a>

### 2.2 Spherical mapping of closed surfaces (with embedded air cavities)

For the surface of the air cavity that requires **Seamless closure**, the B-spline has singularities at the poles. MorphOpt uses a closed surface representation based on **Spherical mapping**:

$$
\mathbf{r} = f(\mathbf{S}; \hat{\mathbf{\Phi}}, \hat{\boldsymbol{\phi}}) = \sum_{i=1}^{n} c_i(\mathbf{S}; \hat{\mathbf{\Phi}})\, \boldsymbol{\phi}^i, \quad \|\mathbf{S}\|_2 = 1
$$

Among them:

- $\mathbf{S}$ serves as the reference point on the unit sphere.
- $\mathbf{\Phi}^i$ represent control points in the reference space (on the unit sphere).
- $\boldsymbol{\phi}^i$ represents the control points in the configuration space (actual 3D coordinates).
- $c_i$ is a normalization weight function. The local support is determined by the distance between points.

$$
c_i(\mathbf{S}; \hat{\mathbf{\Phi}}) = \frac{C_i(\mathbf{S}; \mathbf{\Phi}^i)}{\sum_{j=1}^{n} C_j(\mathbf{S}; \mathbf{\Phi}^j)}
$$

The initial weights are determined using a polynomial of degree 7, ensuring that the function is third-order differentiable everywhere.

$$
C_i(\mathbf{S}; \mathbf{\Phi}^i) = 
\begin{cases}
20\bar{d}^{7} - 70\bar{d}^{6} + 84\bar{d}^{5} - 35\bar{d}^{4} + 1, & \bar{d}^i < 1 \\
0, & \bar{d}^i \ge 1
\end{cases}
$$

Among them, $\bar{d}^i = d(\mathbf{S}, \mathbf{\Phi}^i)/d_0^i$ represents the relative distance, and $d_0^i$ represents the influence radius of the $i$th control point (taking the $k$th nearest neighbor distance).

<a id="section-曲面重建算法"></a>

### 2.3 Surface reconstruction algorithms

During the optimization process, the distribution of control points may become uneven (either too dense or too sparse), leading to numerical instability. MorphOpt introduces the **Periodic surface reconstruction** algorithm to address this issue.

1. **Uniform sowing**: Sampled new points evenly on the surface. The uniform distribution is achieved by minimizing the potential energy of the springs.
2. **Harmonization and refinement**: Maps points onto a plane using stereographic projection. The distribution of points on the plane is optimized before they are projected back onto the sphere.
3. **Minimizing matching errors**: Solving the linear least squares problem to match the new surface with the original surface.

$$
\min_{\hat{\boldsymbol{\psi}}} \sum_{m=1}^{n'} \left[\left\|\mathbf{r}^{m}_\text{opt} - f(\mathbf{\Psi}^{m}; \hat{\mathbf{\Psi}}, \hat{\boldsymbol{\psi}})\right\|^2 + \alpha \left\|\mathbf{r}^m_\text{opt} - \boldsymbol{\psi}^{m}\right\|^2\right]
$$

**Code correspondence**: In `src/morphopt/codesign/offset_boundary_part.py`, the `CPGEOinterface` class implements the logic for surface reconstruction.

---

<a id="section-力学模型"></a>

## 3 Mechanical models

<a id="section-超弹性本构"></a>

### 3.1 Superelasticity Constitutive Law

The soft material used is **Broadly defined Neo-Hookean model**. The strain energy density is:

$$
W = \frac{\mu}{2}(\bar{I}_1 - 3) + \frac{\kappa}{2}(J - 1)^2
$$

Among them:

- $\mu$ represents the shear modulus, while $\kappa$ represents the bulk modulus.
- $\bar{I}_1 = \text{tr}(\mathbf{F}\mathbf{F}^\text{T})J^{-2/3}$ is the first regularization invariant.
- $\mathbf{F}$ represents the deformation gradient, while $J = \det(\mathbf{F})$ represents the volume ratio.

The first Piola-Kirchhoff stress tensor is:

$$
s_{ij} = \frac{\partial W}{\partial F_{ji}} = \mu\left(\frac{1}{J^{2/3}}F_{ji} - \frac{1}{3}\bar{I}_1 F^{-1}_{ij}\right) + \kappa J(J-1)F^{-1}_{ij}
$$

**Example of material parameter configuration:**

```python
class MaterialsParams(morphopt.MaterialsParams):
    def define_interface(self):
        self.add_interface(
            self.HomogeneousMaterial(
                material_parameters=self.materialmodels.NeoHookeanLnJParams(
                    mu=0.482, kappa=4.8),
                density=1.08e-9,
                part_name="body", elementname=""),
            name="body")
```

<a id="section-虚功原理与平衡方程"></a>

### 3.2 The principle of virtual work and equilibrium equations

The static equilibrium of the system is described by the principle of virtual work.

$$
\mathcal{L}(\mathbf{u}, \mathbf{v}) = \mathcal{A}(\mathbf{u}, \mathbf{v}) - \sum_q \mathcal{B}^q(\mathbf{u}, \mathbf{v}) = 0, \quad \forall \mathbf{v} \in U
$$

Among them:

- $\mathcal{A}$ is the internal virtual work: $\displaystyle \mathcal{A}(\mathbf{u}, \mathbf{v}) = \int_{\Omega^0} s_{ij} \frac{\partial v_j}{\partial x_i} \mathrm{d}\Omega$
- $\mathcal{B}^q$ is the virtual work of pressure in cavity $q$: $\displaystyle \mathcal{B}^q(\mathbf{u}, \mathbf{v}) = -p_q \int_{\Gamma_{\text{in}}^{q,0}} (\mathbf{F}^{-1}\mathbf{v})^\text{T} \mathbf{m} J \mathrm{d}\Gamma$
- $\mathbf{u}$ represents the real displacement field, while $\mathbf{v}$ represents the imaginary displacement field.
- $\Omega^0$ refers to the entity field in the initial configuration.

Through finite element discretization (10-node quadratic tetrahedral elements C3D10), the virtual work equations are transformed into an algebraic system of equations:

$$
L_i(\mathbf{U}) = 0
$$

Use the Newton-Raphson method for iterative solution:

$$
\mathbf{U} \leftarrow \mathbf{U} - \mathbf{K}^{-1} \mathbf{L}, \quad K_{ij} = \frac{\partial L_i}{\partial U_j}
$$

**Code correspondence**: In `src/morphopt/optcore/solver.py`, `Solver.solve()` method:

```python
def solve(self):
    result = pools.apply_async(self._solve_FEA, ...)
    # Using the implicit static solver of torchfea
    result: torchfea.solver.StaticResult = fe.solve(...)
```

<a id="section-量纲分析"></a>

### 3.3 Dimensionality analysis

For pneumatic soft robots, deformation is determined solely by **Dimensionless air pressure** $\tilde{p} = p/\mu$, regardless of size. This allows the optimization results to be transferred across different scales.

---

<a id="section-优化问题建模"></a>

## 4 Optimization problem modeling

<a id="section-变形形态设计tro2023morph"></a>

### 4.1 Design of deformable shapes (TRO2023Morph)

The goal of optimization is to make the deformation of the software-controlled robot under pneumatic drive closer to the desired configuration.

$$
\min_{\mathbf{\Phi}} \mathcal{J} = \int_{\Gamma_{\text{RoI}}} \left[ w_{\text{pos}} \|\mathbf{z} - \mathbf{z}^*\|_2^2 + w_{\text{ori}} \|\log(\mathbf{R}^\text{T}\mathbf{R}^*)\|_\text{F}^2 \right] \mathrm{d}\Gamma
$$

Among them:

- $\mathbf{z}, \mathbf{z}^*$ represents the actual location compared to the target location.
- $\mathbf{R}, \mathbf{R}^*$ represents the actual rotation matrix compared to the target one.
- $w_{\text{pos}}, w_{\text{ori}}$ is the weight coefficient.
- Constraints: Equilibrium equations $\mathcal{A}(\mathbf{u}, \mathbf{v}) - \mathcal{B}(\mathbf{u}, \mathbf{v}) = 0$

<a id="section-代码对应-1"></a>

#### 4.1.1 Code correspondence

The objective function is defined through `morphopt.ObjectiveFunction`. The following example demonstrates how to maximize the axial displacement at the end of the structure:

```python
class ObjectiveFunction(morphopt.ObjectiveFunction):
    def objective_function(self):
        return self.fe_results[0].GC[-2]  # Z-component of the end displacement
```

<a id="section-工作空间优化tro2025jacobian"></a>

### 4.2 Workspace optimization (TRO2025Jacobian)

The optimization of the workspace aims to maximize the accessible volume of the end effector. The workspace is divided into several sections:

| Type             | dimension | symbols                            | Description                           |
| ---------------- | ---- | ------------------------------- | ------------------------------ |
| Planar workspace | 2D   | $2\text{A}0\text{R}2\text{T}$ | The reachable areas within the plane $x$ to $z$   |
| Spatial location workspace | 3D   | $3\text{A}0\text{R}3\text{T}$ | 3D accessible spatial environment                |
| Pose workspace     | 2D   | $3\text{A}2\text{R}0\text{T}$ | Direction of pointing at the end (per unit area of the spherical surface)   |
| Pose workspace     | 3D   | $3\text{A}3\text{R}0\text{T}$ | Domain of end-to-end rotation (exponential coordinate volume) |
| Pose-coupled workspace | 3D   | $3\text{A}1\text{R}2\text{T}$ | Planar position + In-plane angle            |

The volume of the workspace is converted into boundary integrals through **Divergence theorem**.

**2D position workspace**  ( $2\text{A}0\text{R}2\text{T}$ ): 

$$
|\mathbb{W}_\text{2T}| = \frac{1}{2} \left|\oint_{\partial \mathbb{P}} \left(U_1 J^{2}_{\zeta_1} - U_2 J^{1}_{\zeta_1}\right) \mathrm{d}\zeta_1\right|
$$

For two-dimensional boundaries, the orientation is counterclockwise, and the components are arranged in the order of the selected response coordinates. For three-dimensional boundaries, the orientation is outward. The numerical implementation involves taking the absolute value of the integral over the complete oriented boundaries, and then constructing the minimization objective using negative signs, weights, and normalization scales.

**3D position workspace**  ( $3\text{A}0\text{R}3\text{T}$ ): 

$$
|\mathbb{W}_\text{3T}| = \frac{1}{3} \int_{\partial \mathbb{P}} \mathbf{U} \cdot (\mathbf{J}_{\zeta_1} \times \mathbf{J}_{\zeta_2}) \, \mathrm{d}\zeta_1 \mathrm{d}\zeta_2
$$

Among them, $\mathbf{J}_{\zeta_k} = \partial \mathbf{U} / \partial \zeta_k$ represents the Jacobi vector at the boundary.

**3D pose workspace** ( $3\text{A}3\text{R}0\text{T}$ , using an approximate representation of exponential coordinates):

$$
|\mathbb{W}_\text{3R}| \approx \frac{1}{24} \int_{\partial \mathbb{P}} \bar{\mathbf{U}} \cdot (\bar{\mathbf{J}}_{\zeta_1} \times \bar{\mathbf{J}}_{\zeta_2}) \, \mathrm{d}\zeta_1 \mathrm{d}\zeta_2
$$

---

<a id="section-灵敏度分析基于自动微分的离散伴随法"></a>

## 5 Sensitivity analysis (using the discrete adjoint method based on automatic differentiation)

<a id="section-设计思路"></a>

### 5.1 Design concept

In collaborative optimization, the dimension of the design variable $\mathbf{\Phi} = [\mathbf{\Phi}_G; \mathbf{\Phi}_M]$ can reach the level of $10^5$. The finite difference method for calculating gradients requires incremental adjustments for each variable and re-running nonlinear finite element analyses, which results in an unacceptable amount of computational effort. MorphOpt uses **Discrete adjoint method based on PyTorch’s automatic differentiation framework** to calculate precise gradients, and the entire sensitivity analysis is automatically performed by the underlying `torchfea` framework.

The design variables $\Phi_m$ affect the system through the finite element assembly process (geometric generation, material interpolation, element assembly), resulting in displacements $U_k$. These displacements, in turn, determine the objective function $\mathcal{J}$. Using the chain rule and the implicit function theorem, by introducing **Auxiliary variables**, the $M$ linear solutions derived from differentiating the $M$ design variables can be compressed into **1–3 linear solves** solutions for the adjoint variables—independent of the number of design variables.

<a id="section-一阶伴随法位移场灵敏度"></a>

### 5.2 First-order adjoint method: Sensitivity of the displacement field

<a id="section-链式法则起点"></a>

#### 5.2.1 Chain rule starting point

The discrete form of the static equilibrium equation is:

$$
R_i(U_k, \Phi_m) = 0
$$

Among them, $U_k$ ($k = 1,\dots,N_{\text{dof}}$) represent the degrees of freedom of node displacements, $\Phi_m$ ($m = 1,\dots,M$) represent the design variables, and $R_i$ represents the residual force vector. The objective function $\mathcal{J}$ depends on the displacement solutions and design variables:

$$
\mathcal{J} = \mathcal{J}(U_k, \Phi_m)
$$

According to the chain rule, the total derivative (sensitivity) is given by:

$$
\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} + \frac{\partial\mathcal{J}}{\partial U_k}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m}
\tag{5.1}
$$

The first item, $\partial\mathcal{J}/\partial\Phi_m$, involves explicit dependencies (such as the regularization term directly containing $\Phi_m$). It can be directly differentiated. The second item contains $\mathrm{d}U_k/\mathrm{d}\Phi_m$, that is, **Implicit derivatives of design variables due to displacement** – directly solving each $m$ requires $M$ linear systems, which is not feasible.

<a id="section-隐函数定理求-mathrmdu_kmathrmdphi_m"></a>

#### 5.2.2 Use the implicit function theorem to find $\mathrm{d}U_k/\mathrm{d}\Phi_m$.

Since the equilibrium equation $R_i = 0$ holds true for any design, its full derivative with respect to $\Phi_m$ is zero:

$$
\frac{\mathrm{d}R_i}{\mathrm{d}\Phi_m} = \frac{\partial R_i}{\partial U_k}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} + \frac{\partial R_i}{\partial\Phi_m} = 0
\tag{5.2}
$$

Define **Tangent stiffness matrix** $K_{ik} \equiv \partial R_i / \partial U_k$ (already assembled in the forward Newton-Raphson convergence step and $LDL^\mathrm{T}$ decomposed). From (5.2):

$$
K_{ik}\,\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} = -\frac{\partial R_i}{\partial\Phi_m}
\quad\Rightarrow\quad
\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} = -K_{kr}^{-1}\,\frac{\partial R_r}{\partial\Phi_m}
\tag{5.3}
$$

<a id="section-伴随变量与总灵敏度"></a>

#### 5.2.3 Dependent variables and overall sensitivity

Substitute (5.3) into (5.1):

$$
\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} - \frac{\partial\mathcal{J}}{\partial U_k}\,K_{kr}^{-1}\,\frac{\partial R_r}{\partial\Phi_m}
\tag{5.4}
$$

Introduce **Auxiliary variables** $\lambda_r$ as the solution for a single linear system:

$$
\boxed{K_{rk}\,\lambda_r = -\frac{\partial\mathcal{J}}{\partial U_k}}
\tag{5.5}
$$

(The symmetry of $K_{rk}=K_{kr}$ under conservative loads has been exploited using hyperelastic materials.) Equivalently, $\lambda_r = -K_{rk}^{-1}\,\partial\mathcal{J}/\partial U_k$. Substituting into (5.4) yields the compact **General sensitivity formula**:

$$
\boxed{\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} + \lambda_r\,\frac{\partial R_r}{\partial\Phi_m}}
\tag{5.6}
$$

<a id="section-计算步骤总结"></a>

#### 5.2.4 Summary of calculation steps

| steps | Operation/action | Computational complexity |
|------|------|--------|
| **Step 1** | Automatic differentiation for $\partial\mathcal{J}/\partial U_k$ | One backpropagation iteration |
| **Step 2** | Solving the adjoint equation $K_{rk}\lambda_r = -\partial\mathcal{J}/\partial U_k$ | Previous generation/iteration number (Reused for $K$). |
| **Step 3** | Calculated between $\partial R_r/\partial\Phi_m$ and $\partial\mathcal{J}/\partial\Phi_m$. | One backward propagation along the computational graph |
| **Step 4** | The combination is $\mathrm{d}\mathcal{J}/\mathrm{d}\Phi_m$. | Inner product; can be ignored |

This process requires solving **An additional system of linear equations**. Compared to the finite difference method, the computational cost is reduced from $\mathcal{O}(M \cdot N_{\text{dof}}^2)$ to $\mathcal{O}(N_{\text{dof}}^2)$, and this does not depend on the number of design variables, which is $M$.

---

<a id="section-二阶伴随法雅可比灵敏度"></a>

### 5.3 Second-order adjoint method: Jacobian sensitivity

<a id="section-问题扩展"></a>

#### 5.3.1 Problem extension

For the optimization of the working space and the design involving multiple load case combinations, the objective function may depend not only on the displacement $U_i$, but also on **Continuum Jacobian matrix** – the derivative of the displacement with respect to the load parameters (air pressure):

$$
J_{in} \equiv \frac{\partial U_i}{\partial p_n}
\tag{5.7}
$$

At this point, the objective function becomes:

$$
\mathcal{J} = \mathcal{J}(U_i,\, J_{in},\, \Phi_m)
\tag{5.8}
$$

The chain rule has added one more item:

$$
\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} + \frac{\partial\mathcal{J}}{\partial U_k}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} + \frac{\partial\mathcal{J}}{\partial J_{in}}\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m}
\tag{5.9}
$$

The first two items are handled using the first-order adjoint method. The challenge lies in the third item: it is necessary to obtain the derivative of the Jacobian matrix with respect to the design variables $\mathrm{d}J_{in}/\mathrm{d}\Phi_m$.

<a id="section-雅可比矩阵的定解方程"></a>

#### 5.3.2 The solution equations of the Jacobian matrix

Derivative of the equilibrium equation $R_j(U_i, \Phi_m, p_n) = 0$ with respect to the air pressure parameter $p_n$ (with $\Phi_m$ fixed):

$$
\frac{\partial R_j}{\partial U_i}\frac{\partial U_i}{\partial p_n} + \frac{\partial R_j}{\partial p_n} = 0
\quad\Rightarrow\quad
K_{ji}\,J_{in} + \frac{\partial R_j}{\partial p_n} = 0
\tag{5.10}
$$

That is, $J_{in} = -K_{ij}^{-1}\,\partial R_j/\partial p_n$. This is the definite equation that $J_{in}$ must satisfy.

<a id="section-雅可比矩阵对设计变量的全导数"></a>

#### 5.3.3 Jacobian matrices and the full derivatives of design variables

Derive the full derivatives of equation (5.10) with respect to the design variable $\Phi_m$. Here, $K_{ji}$ and $\partial R_j/\partial p_n$ explicitly depend on $\Phi_m$ and implicitly depend on $U_k(\Phi_m)$.

$$
\begin{aligned}
&K_{ji}\,\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} 
+ \left(\frac{\partial K_{ji}}{\partial\Phi_m} + \frac{\partial K_{ji}}{\partial U_k}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m}\right) J_{in} \\
+ &\left(\frac{\partial^2 R_j}{\partial\Phi_m\partial p_n} + \frac{\partial^2 R_j}{\partial U_k\partial p_n}\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m}\right) = 0
\end{aligned}
\tag{5.11}
$$

Introduce the **Total differential operator** $\mathrm{d}/\mathrm{d}p_n$ regarding $p_n$: For any $Q(U_k(\Phi_m, p_n), \Phi_m, p_n)$, there exists $\mathrm{d}Q/\mathrm{d}p_n =(\partial Q/\partial U_k)J_{kn} + \partial Q/\partial p_n$. Use this operator to combine like terms in (5.11):

$$
K_{ji}\,\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} = -\frac{\mathrm{d}K_{jk}}{\mathrm{d}p_n}\,\frac{\mathrm{d}U_k}{\mathrm{d}\Phi_m} - \frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_j}{\mathrm{d}p_n}\right)
\tag{5.12}
$$

Substitute $\mathrm{d}U_k/\mathrm{d}\Phi_m = -K_{kr}^{-1}\,\partial R_r/\partial\Phi_m$ (from (5.3)), and multiply it by $K_{ij}^{-1}$ on the left side:

$$
\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} = K_{ij}^{-1}\,\frac{\mathrm{d}K_{jk}}{\mathrm{d}p_n}\,K_{kr}^{-1}\,\frac{\partial R_r}{\partial\Phi_m} - K_{ij}^{-1}\,\frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_j}{\mathrm{d}p_n}\right)
\tag{5.13}
$$

<a id="section-二阶伴随变量"></a>

#### 5.3.4 Second-order adjoint variables

Substitute (5.13) for the third term in (5.9):

$$
\frac{\partial\mathcal{J}}{\partial J_{in}}\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial J_{in}}K_{ij}^{-1}\,\frac{\mathrm{d}K_{jk}}{\mathrm{d}p_n}\,K_{kr}^{-1}\,\frac{\partial R_r}{\partial\Phi_m} - \frac{\partial\mathcal{J}}{\partial J_{in}}K_{ij}^{-1}\,\frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_j}{\mathrm{d}p_n}\right)
\tag{5.14}
$$

To avoid explicitly constructing and storing large third-order tensors $\mathrm{d}K_{jk}/\mathrm{d}p_n$, two additional adjoint variables are introduced. **First Jacobi companion variable** $\lambda_{rn}^*$:

$$
\boxed{K_{rj}\,\lambda_{rn}^* = -\frac{\partial\mathcal{J}}{\partial J_{jn}}}
\tag{5.15}
$$

That is, $\lambda_{rn}^* = -K_{rj}^{-1}\,\partial\mathcal{J}/\partial J_{jn}$.

**Second Jacobi companion variable** $\lambda_i^{**}$, combine $\lambda_{rn}^*$ with the full derivative of the stiffness matrix to form the right-hand side term:

$$
\boxed{K_{is}\,\lambda_s^{**} = \frac{\mathrm{d}K_{rs}}{\mathrm{d}p_n}\,\lambda_{rn}^*}
\tag{5.16}
$$

That is, $\lambda_s^{**} = K_{si}^{-1}\,(\mathrm{d}K_{ri}/\mathrm{d}p_n)\,\lambda_{rn}^*$. The right-hand term is calculated per element and then assembled. **No need to do anything** explicitly stores the complete $\mathrm{d}K/\mathrm{d}p_n$ tensor.

Substituting (5.14) into the equation, we get:

$$
\frac{\partial\mathcal{J}}{\partial J_{in}}\frac{\mathrm{d}J_{in}}{\mathrm{d}\Phi_m} = \lambda_i^{**}\,\frac{\partial R_i}{\partial\Phi_m} + \lambda_{rn}^*\,\frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_r}{\mathrm{d}p_n}\right)
\tag{5.17}
$$

<a id="section-完整二阶伴随灵敏度"></a>

#### 5.3.5 Complete second-order adjoint sensitivity

Combining the results of the first-order adjoint method (5.6) and the Jacobian correction (5.17), we obtain **The complete second-order adjoint sensitivity formula**:

$$
\boxed{\frac{\mathrm{d}\mathcal{J}}{\mathrm{d}\Phi_m} = \frac{\partial\mathcal{J}}{\partial\Phi_m} + \lambda_r\,\frac{\partial R_r}{\partial\Phi_m} + \lambda_i^{**}\,\frac{\partial R_i}{\partial\Phi_m} + \lambda_{rn}^*\,\frac{\partial}{\partial\Phi_m}\!\left(\frac{\mathrm{d}R_r}{\mathrm{d}p_n}\right)}
\tag{5.18}
$$

The physical meanings of the four items:

| Item number | expression | Physical meaning |
|------|--------|---------|
| ① | $\partial\mathcal{J}/\partial\Phi_m$ | The explicit dependence of the objective function on the design variables |
| ② | $\lambda_r\,\partial R_r/\partial\Phi_m$ | Displacement-stiffness coupling sensitivity (first-order adjoint) |
| ③ | $\lambda_i^{**}\,\partial R_i/\partial\Phi_m$ | Jacobi-Stress Coupling Sensitivity (Second-order Conjugate) |
| ④ | $\lambda_{rn}^*\,\partial(\mathrm{d}R_r/\mathrm{d}p_n)/\partial\Phi_m$ | Jacobi-load coupling sensitivity (first-order Jacobi adjoint) |

When the objective function does not contain Jacobian dependencies ($\partial\mathcal{J}/\partial J_{in}=0$), then $\lambda_{rn}^*=0$, $\lambda_i^{**}=0$, and (5.18) automatically reduce to (5.6).

<a id="section-计算效率"></a>

#### 5.3.6 Computational efficiency

The three adjoint equations (5.5), (5.15), and (5.16) share the same tangent stiffness matrix $K_{ij}$. During the forward Newton-Raphson iteration, the decomposition of $LDL^\mathrm{T}$ has been completed. Each adjoint equation only requires one forward/backward iteration (the forward iteration of $< 5\%$ takes time). All partial derivatives $\partial R_i/\partial\Phi_m$ and $\partial(\mathrm{d}R_r/\mathrm{d}p_n)/\partial\Phi_m$ are obtained through a single backward propagation along the computational graph. Geometric generation, material interpolation, and element assembly are all expressed as tensor operations that are differentiable with respect to $\Phi_m$.

**Final conclusion: No matter how large the number of design variables $M$ is, a complete second-order adjoint sensitivity analysis only requires 1–3 additional linear calculations in each outer iteration. The computational cost is independent of $M$.**

<a id="section-morphopt-中的灵敏度工作流"></a>

### 5.4 Sensitivity workflow in MorphOpt

In the MorphOpt framework, the above calculations were performed automatically by `sensitivity_analysis()`.

1. **Obtain design variables**: Call `params.obtain_design_sensitivity_vars()` to merge the geometric control point $\mathbf{\Phi}_G$ with the material density control point $\mathbf{\Phi}_M$ into a unified design vector.
2. **Defining differentiable mappings**: `apply_func` callback applies design variables to the assembly (modifies node coordinates, updates material properties). All operations ensure that the PyTorch computational graph remains traceable.
3. **Call the sensitivity solver**: `solver.get_jacobian_sensitivity_multistep()` Auto-complete functionality:
   - Automatic differential calculation for $\partial\mathcal{J}/\partial U_k$ and $\partial\mathcal{J}/\partial J_{in}$
   - Assemble and solve the accompanying system of equations (5.5), (5.15), and (5.16).
   - Propagate all partial derivatives along the reverse direction of the computational graph.
   - Combining according to (5.18) yields a total sensitivity of $\mathrm{d}\mathcal{J}/\mathrm{d}\Phi_m$.
4. **Gradient splitting**: The overall gradient is first split into geometric and material components. The geometric components are then processed in **Slice the data according to the Part structure.**, and each component is sent to its respective `UpdaterBoundaryPart` (each component is bound to a boundary Part) and `UpdaterSIMPMaterial` sub-optimizers.

**Code correspondence**: `ObjectiveFunction.sensitivity_analysis()` methods in `src/morphopt/optcore/objfunc.py`.

<a id="section-灵敏度从-fea-节点到控制点的映射"></a>

### 5.5 The mapping from finite element nodes to design parameters

The geometric interface maps the design parameter $\theta$ to the boundary node coordinates $X_b(\theta)$. The matched UVs and basis functions are fixed on the current grid. The adjoint sensitivity is transmitted along this mapping and the model modification path:

$$
\frac{\mathrm dJ}{\mathrm d\theta}
=\left(\frac{\partial X_b}{\partial\theta}\right)^T
\frac{\mathrm dJ}{\mathrm dX_b}
+\text{remaining explicit design terms}.
$$

`ObjectiveFunction.sensitivity_analysis()` returns the design parameter gradients organized by geometry, load, and material arrangements. The updater manager then assigns the corresponding slices based on the Part. `ShapeDerivative.initialize()` directly splits the original slice into `get_surface_parameters()` dimensions for each surface. No nearest-neighbor interpolation from the node gradients to the control points is performed, and no normalization is carried out.

BSP/CPGEO reuse its existing basis function mapping. The selected NURBS surfaces in BREP reuse `bspmap.Basis` to construct rational basis functions and node UV mapping. After the surface is re-partitioned, the nodes are re-matched, and the parameters, gradients, and update writing order are kept consistent.

Nearest neighbor interpolation is only used for the optional `SensitivityShapeUpdate` geometric penalty term sampling weights; it does not replace the chain rule of physical sensitivity. The second-order proxy also uses the original parameter gradients to construct the curvature history.

The entry points are `shapeopt/boundary_part.py`, `shapeopt/objectivefuncs/shapederivative.py`, and corresponding surface mapping classes.

<a id="section-工作空间优化与连续体雅可比矩阵"></a>

## 6 Workspace optimization and the continuum Jacobian

<a id="section-连续体雅可比定义"></a>

### 6.1 Continuum Jacobi definition

For soft robotic robots, their kinematics are **implicative** (determined by nonlinear continuum mechanics), and explicit positive kinematics cannot be written. Therefore, **Continuum Jacobian matrix** is defined as follows:

$$
J^i_{p_r} = \frac{\partial U_i}{\partial p_r}
$$

Among them, $U_i$ represents the $i$st degree of freedom of the end effector (3 translations + 3 rotations), and $p_r$ is the air pressure in the $r$rd air chamber.

This Jacobian maps the volume integral of the working space from the unknown configuration space to the preset air pressure space. Using the divergence theorem, the numerical integration only involves solving the problems at the boundaries of the driving parameter domain:

$$
|\mathbb{W}| = \int_{\mathbb{W}} \mathrm{d}\mathbf{U} = \int_{\partial \mathbb{P}} w(\mathbf{U}, \mathbf{J}) \,\mathrm{d}\zeta
$$

<a id="section-驱动边界上的高斯求积"></a>

### 6.2 Gaussian quadrature on driving boundaries

The Quickstart allows selecting independent inputs from the air cavity pressure channels to participate in the workspace integration; for air cavities connected in the same channel, the unselected channels are fixed at zero pressure. For the selected $d$-dimensional driving parameter domain, Quickstart uses the Gauss–Legendre quadrature method on each edge or surface at the boundary $\partial\mathbb{P}$. Each Gaussian point on the boundary corresponds to an FEA load case, and the Jacobian array indicates the rate of change at the end of that boundary. The discrete objective is:

$$
\max_{\boldsymbol{\phi}} \mathcal{T} = \sum_{g=1}^{k} \tau^g w_X(\mathbf{U}^g, \mathbf{J}^g)
$$

Among them, $g$ represents the Gaussian points on the boundary. $\tau^g$ includes the integration weights derived from the mapping of physical pressure intervals and the orientation of the boundary. $w_X$ is the integral function corresponding to the divergence theorem in the corresponding dimension. In a two-dimensional driving domain with four sides, if $n$ points are used for each side, then $4n$ load cases can be generated. In a three-dimensional driving domain with six faces, if $n$ points are used for each of the two coordinate directions within each face, then $6n^2$ load cases can be generated. Increasing $n$ can refine the boundary integration, eliminating the need to place Gaussian points within the driving domain.

The example paper uses a fixed number of integration points for each type of work space. The table below records the settings used in the paper. The Quickstart uses a uniform rule for edge/face tensor products, and the number of samples is determined by the user-selected $n$:

| Workspace type                    | Gaussian points | Description                  |
| ------------------------------- | -------- | --------------------- |
| $2\text{A}0\text{R}2\text{T}$ | 4        | 2-point Gaussian integral on the boundary |
| $3\text{A}0\text{R}3\text{T}$ | 6        | Reducing the amount of symmetry used        |
| $3\text{A}2\text{R}0\text{T}$ | 2        | Integrals on boundary curves      |
| $3\text{A}3\text{R}0\text{T}$ | 8        | Unsymmetric total area integral    |
| $3\text{A}1\text{R}2\text{T}$ | 24       | Unsymmetric total area integral    |

<a id="section-工作空间形状设计扩展"></a>

### 6.3 Extended design options for workspace shapes

By introducing non-uniform weight functions, the workspace optimization can be extended to **Shape design**. For example, higher weights can be assigned to the desired pose regions, thereby directing the optimization results towards those specific regions of the workspace.

---

<a id="section-几何约束"></a>

## 7 Geometric constraints

To ensure the **Manufactability** and **Numerical stability** of the optimization results, MorphOpt integrates various geometric constraints, which are incorporated into the sub-optimization problem in the form of **penalty function**.

<a id="section-最小距离约束"></a>

### 7.1 Minimum distance constraint

Prevent penetration and excessive thinning between different surfaces, or within the same surface.

$$
g(\mathbf{r}^m, \mathbf{r}^n) = t^*_{mn} - \|\mathbf{r}^m - \mathbf{r}^n\| \leq 0
$$

The derivative is:

$$
\frac{\partial g}{\partial \mathbf{P}_{ij}} = -\frac{B_i^q B_j^r (\mathbf{r}^m - \mathbf{r}^n)}{\|\mathbf{r}^m - \mathbf{r}^n\|}
$$

**Code correspondence**: There are `Distance` classes in `src/morphopt/shapeopt/objectivefuncs/distancesurface.py`.

<a id="section-曲率约束"></a>

### 7.2 Curvature constraints

Restricting principal curvatures $k_1, k_2$ To prevent stress concentration and grid distortion:

$$
h_1(q,r) = \frac{1}{2}(k_1^2 + k_2^2) = 2H^2 - K
$$

Here, $H$ represents the average curvature, while $K$ represents the Gaussian curvature.

In the `codesign` sub-module, there is also the **Inner curvature radius constraint** that is designed for shell structures. Ensure that the offset surfaces do not intersect themselves.

```python
class InwardCurvatureRadius(BaseConstraints):
    """Limit the inward principal curvature: k_inward <= 1 / (thickness + margin)"""
```

<a id="section-曲面光顺性约束"></a>

### 7.3 Curved surface smoothness constraints

**Angle constraints**: The punishment vector deviates from the orthogonal direction.

$$
h_2(q,r) = \cos^2(\theta) = \frac{F^2}{EG}
$$

**Uniformity constraint**: Calculates the gradient of the penalty term related to the length of the cutting vector, ensuring that the control points are distributed evenly.

$$
h_3(q,r) = \frac{E_q^2 + E_r^2}{4\tau_q^2 E^2} + \frac{G_q^2 + G_r^2}{4\tau_r^2 G^2}
$$

**Code correspondence**: There are `Fairness` classes in `src/morphopt/shapeopt/objectivefuncs/surfacefairness.py`.

<a id="section-边界约束"></a>

### 7.4 Boundary constraints

Restrictions on curved surfaces within the design domain (e.g., when the boundary is a cylinder):

```python
class Cylinder(BaseConstraints):
    """Constrain points to the cylinder (radius, height, bottom)."""
```

**Code correspondence** :  `src/morphopt/shapeopt/objectivefuncs/boundarys.py` .

<a id="section-罚函数形式"></a>

### 7.5 Form of penalty function

All constraints are transformed into unconstrained problems using the unified **Obstacle function**.

$$
f(x) = 
\begin{cases}
0, & x \leq 0 \\
x^b, & x > 0
\end{cases}
$$

The currently built-in geometric penalty uses $b=3$, which is second-order continuous at the active boundary. Its threshold and transition regions are defined by the specific penalty terms. The positive function is applied to the dimensionless violation quantity, and physical quantities cannot be directly combined without dimensioning. The reference surface integral, sampling factors, and overall coefficients are defined separately, see [Policy and Points Interface](../script-reference.md#section-几何更新策略与障碍积分).

---

<a id="section-子优化与信赖域方法"></a>

## 8 Design subproblems and local surrogate models

<a id="section-动机"></a>

### 8.1 motivation

After each finite element and sensitivity analysis, MorphOpt constructs local proxies. The proxy objectives and geometric penalties are evaluated during the inner solution process. The update strategy determines the upper limit of the step size for the design variables. Based on the results of the local solution, the design proposed for the current round is selected. In the next round of FEA, the physical responses are recalculated using this design.

<a id="section-子优化问题"></a>

### 8.2 Suboptimal optimization problems

The sub-optimization problem is defined as follows:

$$
\min_{\vec{\Psi}} \tilde{\mathcal{L}}^k = \underbrace{\frac{\partial \mathcal{L}}{\partial \mathbf{\Phi}}^k \cdot \vec{\Psi}}_{\text{surrogate objective}} + \underbrace{\sum \text{Penalty}(\text{constraint})}_{\text{constraint penalty}}
$$

Among them, $\vec{\Psi} = \mathbf{\Phi}^{k+1} - \mathbf{\Phi}^k$ represents the change in the design variables.

`ShapeDerivative()` represents the original first-order proxy; the independent objective class `QuadraticShapeDerivative(memory_size=10)` adds a historical curvature term to the first-order physical objective:

$$
\tilde{\mathcal L}^k(\vec\Psi)
=g_k^T\vec\Psi+\frac12\vec\Psi^T B_k^{\mathrm{FEA}}\vec\Psi
+\sum\operatorname{Penalty}(\text{constraint}).
$$

Among them, $s_k=\Phi_k-\Phi_{k-1}$ and $y_k=g_k-g_{k-1}$ come from the outer finite element observations. Both the physical proxy and historical differences use the original finite element gradient, without any sensitivity scaling. The finite memory directly constructs $B_k^{\mathrm{FEA}}$ using BFGS updates, retaining only the curvature pairs that satisfy $s_k^Ty_k>10^{-8}\|s_k\|\|y_k\|$. When there is no valid historical data, no quadratic terms are added. This positive definite approximation ignores the negative curvature in the actual objective.

This curvature and the quasi-Newton information of the inner solver belong to different iteration levels: the former approximates the true finite element objective, while the latter approximates the sum of the current agent and penalty terms. Both are used together, but each retains its independent history. The specific objective definitions are located at `shapeopt/objectivefuncs/shapederivative.py` Share historical calculations with others. `QuadraticHistory` Located in `src/morphopt/optcore/updaters.py` For details on parameters and the persistence interface, please refer to… [Script module and API reference](../script-reference.md#section-有限元目标的历史梯度二阶代理) .

<a id="section-l-bfgs-求解器"></a>

### 8.3 L-BFGS solver

The sub-optimization uses the **Limited memory BFGS (L-BFGS) method** method:

$$
\vec{\Psi}^{l+1} = \vec{\Psi}^l - \alpha_l B_l^{-1} \nabla \tilde{\mathcal{L}}^k
$$

Among them, $B_l^{-1}$ represents the inverse approximation of the Hessian for the current subproblem. The BFGS update formula is as follows:

$$
B^{-1}_{l+1}=(I-\rho_l s_l y_l^T)B^{-1}_l(I-\rho_l y_l s_l^T)+\rho_l s_l s_l^T,
\qquad \rho_l=(y_l^Ts_l)^{-1}.
$$

$\mathbf{s}_l = \vec{\Psi}^{l+1} - \vec{\Psi}^l$ represents the step size vector, while $\mathbf{y}_l$ represents the gradient change vector.

**Code correspondence**: In `src/morphopt/optcore/updaters.py`, there is a `BaseUpdater.Optimizer.LBFGS` class:

```python
class LBFGS(BaseOpt):
    def __init__(self, closure, num_limit=10):
        super().__init__(closure)
        self.history = QuadraticHistory(memory_size=num_limit)

    def step(self, x_now, gk_now=None):
        # The parameters and gradients of the sub-problem were recorded for the first time.
        # Calculate the search direction for history.inverse_hessian_product(-gk_now)
        # Armijo backtracking line search to determine the step size
        # After accepting the trial step, history.observe(x_new, gk_new) is updated for the inner history.
        ...
```

`QuadraticHistory` uniformly implements finite memory curvature for management and two-loop recursion. The inner gradient comes from the complete subproblem, including physical agents and geometric penalty terms; the gradient of the outer second-order objective comes from finite element analysis. The two instances use different parameter coordinates and are updated independently, and they cannot share the same history.

<a id="section-回溯线搜索"></a>

### 8.4 Backtracking line search

Step Length $\alpha_l$ is determined through backtracking search, with the condition that the algorithm satisfies Armijo conditions.

$$
f(\mathbf{x} + \alpha \mathbf{d}) < f(\mathbf{x}) + c_1 \alpha \nabla f(\mathbf{x})^\text{T} \mathbf{d}
$$

<a id="section-收敛判据与自适应策略"></a>

### 8.5 Convergence criteria and adaptive strategies

Suboptimal optimization convergence criterion (choose one of the options below):

- $\alpha_k < \epsilon_\alpha$ – The step size is too small.
- $l > \aleph^k$ (maximum number of iterations reached)

Parameter `max_step_iter` specifies the upper limit of iterations for a single local solution. `max_step_length` specifies the upper limit of the physical step size, and the built-in strategy updates the actual change in constraints through the `atan` mapping of the updater. The first-order and second-order agents share the same update strategy interface. The adaptive shape update is limited by the total number of sub-solutions per round by `max_solves`. Each solution uses the same step size limit and continues from the end point of the previous solution. The strategy adjusts the penalty value based on local overshoot conditions between two solutions, and the last solution enters the next round.

---

<a id="section-数值流程"></a>

## 9 Numerical processes

<a id="section-整体优化循环"></a>

### 9.1 Overall optimization cycle

```
Algorithm: MorphOpt morphological optimization process
———————————————————————————————————
while Not converged:
    # 1. Geometric modeling
    Generating B-spline surface/spheroidal mapping surfaces based on control points
    Exporting geometry files (STP) for mesh generation
  
    # 2. Finite element analysis
    Using GMSH to generate tetrahedral meshes (C3D10H)
    Apply the Neo-Hookean material model
    Application load (air pressure) and boundary conditions
    Solving for static equilibrium using Newton-Raphson method
  
    # 3. Sensitivity analysis (automatic differentiation)
    Obtain design variables (control point coordinates).
    Defined apply_func: Design variables. → Modify the assembly
    Defined compute_objective_func: Objective function.
    Call solver.get_jacobian_sensitivity_multistep()
    ├── Automatic differentiation: calculating ∂Obj/∂U.
    ├── Solving adjoint equations (reusing the stiffness matrix decomposition method)
    └── Automatically send the gradient back to the control point.
  
    # 4. Solve the design subproblem with a local surrogate and step bounds.
    Constructing the proxy function (first-order Taylor expansion or gradient history-based proxy + constraint terms).
    L-BFGS Iterative subproblem solving
    Backtracking line search to determine the step size
  
    # 5. Update and save
    Update control point coordinates.
    Solving for ShapeDerivative interpolation coefficients
    Save historical records
    Perform surface reconstruction after a certain number of steps.
———————————————————————————————————
```

<a id="section-代码架构对应"></a>

### 9.2 Code architecture correspondence

```
Controller                    → Optimized main loop control (optcore/controller.py)
├── Params                    → Parameter Management (optcore/modelparams/params.py)
│   ├── GeometryParams        → A group of Part interfaces (each Part = one PartInterface)
│   │   ├── BoundaryPart (BSP/Spherical mapping surfaces, suitable for optimization purposes.
│   │   ├── INPPart (Fixed geometry)
│   │   └── Each Instance of the Part is automatically named as <part>-1, <part>-2, …
│   ├── FEAParams             → FEA Parameters (loading step, BC, RP)
│   └── Materials             → Material parameters (μ, κ, ρ)
├── Solver                   → FEA Parallel solving (optcore/solver.py)
│   └── torchfea.solver       → Implicit static solver + adjoint solution method
├── ObjectiveFunction         → Objective function + sensitivity analysis (optcore/objfunc.py)
│   ├── compute_multistep_objective() → Definition of objectives for various operating conditions
│   ├── sensitivity_analysis()        → Automatic differential sensitivity calculation
│   │   └── solver.get_jacobian_sensitivity_multistep()
│   │       ├── apply_func (Modify the assembly.)
│   │       ├── compute_objective_funcs (Target callback)
│   │       ├── Automated solution generation (reusing K-matrix decomposition techniques)
│   │       └── autograd Sending gradients back to the control point
│   └── Jacobian                  → Jacobian information in the results (fe_result.jacobian)
└── Updaters                  → Sub-optimalizer dictionary (optcore/updaters.py)
    │                          define_updater() Use add_geometry_updater() for this purpose. /
    │                          add_geometry_updater() / add_material_updater() Classification statement,
    │                          Default name: <ClassName>_<Number>
    ├── UpdaterBoundaryPart[i]  → Each boundary: Part one (shapeopt/update_boundary_part.py)
    │   ├── part_name         → Boundaries of the part to be bound (resolved during initialization; gradients are sliced by part)
    │   │                       Load case (stored in log/geometryupdater/<part_name>/)
    │   ├── ShapeDerivative   → Shape derivative objective (objectivefuncs/shapederivative.py)
    │   ├── Distance          → Minimum distance constraint (objectivefuncs/distancesurface.py)
    │   ├── Fairness          → Surface Fairness Constraint (objectivefuncs/surfacefairness.py)
    │   └── Cylinder/MinRadius → Boundary constraints (objectivefuncs/boundarys.py)
    ├── UpdaterSIMPMaterial[i]   → One for each designable material interface (simp/update_simpmaterial.py)
    │   └── interface_name    → The material interfaces that are bound to it (gradients are divided into individual interfaces).
    │                           State stored in log/materialupdater/<interface_name>/
    └── LBFGS                 → Suboptimal solver (updaters/optimizer.py)
```

> Test environment: Intel Core i9-12900K, NVIDIA Titan V, 128 GB RAM.

---

<a id="section-参考文献"></a>

## 10 References

1. **Chen F, Song Z, Chen S, Gu G, Zhu X.** *Morphological Design for Pneumatic Soft Actuators and Robots with Desired Deformation Behavior.* IEEE Transactions on Robotics, 2023.
2. **Song Z, Chen F, et al.** *Continuum Jacobian based Computational Morphogenesis for Soft Robotic Workspace Optimization.* IEEE Transactions on Robotics, 2026.
3. Choi K K, Kim N-H. *Structural Sensitivity Analysis and Optimization 1: Linear Systems.* Springer, 2006.

<a id="section-几何罚项的离散积分与权重"></a>

## 11 Discrete integration of geometric penalty terms and weights

On the outer reference surface, discrete geometric penalties are applied with reference area weights. In each subproblem, these areas are kept fixed. The point-by-point sensitivity strategy introduces sampling factors, and the integral strategy applies named coefficients after integration. The physical objective gradient remains at its original scale. The penalty terms for distance pairs use the product of the integration weights on both sides. The discrete results are still affected by sampling and neighborhood filtering errors. The integral form does not mean that values will be exactly the same under arbitrary coarse sampling.

The adaptive geometric strategy initially expands the transition band of the geometric penalty terms, and then gradually narrows it based on the degree of sampling violation of the initial geometry. Each penalty term follows its own exponential function. The coefficients are adjusted according to the degree of sampling violation and the norm of the physical objective gradient in the subproblem coordinates, and remain fixed during the solution of a single subproblem.
