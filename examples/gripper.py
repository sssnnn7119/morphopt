
from operator import index

import morphopt
import numpy as np
import torch
import torchfea
mumax = 10.
minratio = 1e-7


class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='/run/media/song/缓存/results/', 
                         opt_label='BeamMinEnergy')
        
    class ObjectiveFunction(morphopt.simp.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def get_volume_fraction(self):
            elems = self.fe.assembly._parts['final_model'].elems['C3D8']

            materials = elems.materials

            mu = materials['material-0']._mu
            gaussian_weight = elems.gaussian_weight  # [gaussian, element]

            ratio_now = (mu - mumax * minratio) / (mumax * (1 - minratio))
            ratio_now = ratio_now.clamp(0.0, 1.0)

            volume = gaussian_weight * ratio_now
            volume_total = gaussian_weight.sum()

            volume_fraction = volume.sum() / volume_total

            return volume_fraction

        def objective_function(self):
            self.set_step(0)
            total_force = self.fe.assembly._assemble_generalized_Matrix(GC=self.fe_results[0].GC)[0]

            ins_gripper = self.fe.assembly.get_instance('final_model')
            RGC_index_start = self.fe.assembly._RGC_list_indexStart

            force_gripper = total_force[RGC_index_start[ins_gripper._RGC_index]:RGC_index_start[ins_gripper._RGC_index+1]].reshape([-1, 3])

            # return torch.exp(force_gripper[:, 0].sum()) - force_gripper[:, 2].sum()



            RGCindex_RPxmax = self.fe.assembly.get_reference_point('RPXmax')._RGC_index
            RGC = self.fe.GC2RGC(self.fe_results[0].GC)
            RPXmax_disp = RGC[RGCindex_RPxmax]
            return RPXmax_disp[-2] + torch.exp(force_gripper[:, 0].sum()) - force_gripper[:, 2].sum()

        def get_metrics(self):
            total_force = self.fe.assembly._assemble_generalized_Matrix(GC=self.fe_results[0].GC)[0]

            ins_gripper = self.fe.assembly.get_instance('final_model')
            RGC_index_start = self.fe.assembly._RGC_list_indexStart

            force_gripper = total_force[RGC_index_start[ins_gripper._RGC_index]:RGC_index_start[ins_gripper._RGC_index+1]].reshape([-1, 3])

            return [force_gripper[:, 0].sum(), force_gripper[:, 2].sum(), self.get_volume_fraction()]

    class Params(morphopt.simp.Params):
        class GeometryParams(morphopt.simp.FixedGeometry):

            def define_assembly(self):
                part = torchfea.cad.create_box(xmin=0.0, xmax=80.0, ymin=-0.5, ymax=0.5, zmin=-30.0, zmax=0.0, nx=161, ny=2, nz=61)
                part.add_surface_set('surface_0_All', part.elems['C3D8'].extract_boundary_surface_set())


                # part.convert_linear_to_quadratic_elements(element_name_list=['C3D8'], new_element_name_list=['C3D8'])
                instance = torchfea.Instance(part_name='final_model')
                instance.external_surface = 'surface_0_All'
                assembly = torchfea.Assembly()
                assembly.add_part(part, name='final_model')
                assembly.add_instance(instance, name='final_model')


                import gmsh
                gmsh.initialize()
                gmsh.clear()

                gmsh.model.add("cylinderobject")
                gmsh.model.occ.addCylinder(65, -10, 15, 0, 20, 0, 15, tag=1)
                gmsh.model.occ.synchronize()

                # mesh the geometry
                gmsh.option.setNumber("Mesh.MeshSizeMin", 1.0)
                gmsh.option.setNumber("Mesh.MeshSizeMax", 1.5)

                gmsh.model.mesh.generate(3)
                
                node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
                nodes = torch.tensor(node_coords, dtype=torch.float64).reshape(-1, 3)

                elementTypes, elementTags, nodeTags = gmsh.model.mesh.getElements()
                tet_tags = None
                for etype, etags, ntag in zip(elementTypes, elementTags, nodeTags):
                    if etype == 4:
                        tet_tags = np.array(etags, dtype=np.int64)
                        elems = torch.tensor(ntag, dtype=torch.int64).reshape(-1, 4) - 1
                        break


                part_cylinder = torchfea.Part(nodes=nodes)
                elems_cylinder = torchfea.elements.initialize_element(element_type='C3D4', elems_index=torch.arange(elems.shape[0]), elems=elems)
                part_cylinder.add_element(elems_cylinder, name='C3D4')


                part_cylinder.add_surface_set('extern', part_cylinder.elems['C3D4'].extract_boundary_surface_set())
                part_cylinder.add_node_set('cylinder', np.arange(nodes.shape[0]))

                
                instance_cylinder = torchfea.Instance(part_name='cylinder')
                instance_cylinder.external_surface = 'extern'
                assembly.add_part(part_cylinder, name='cylinder')
                assembly.add_instance(instance_cylinder, name='cylinder')

                return assembly
                

        class FEAParams(morphopt.simp.FEAParams):

            def define_interface(self):
                # Boundary the xmin as base
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 0.]), name='RPBase')
                self.add_fea_interface(self.CoupleInterface(rp_name='RPBase', instance_name='final_model', set_nodes_name='nodes_xmin'))
                self.add_fea_interface(self.BoundaryConditionRPInterface(rp_name='RPBase', index_dof=[0, 1, 2, 3, 4, 5]), name='BC_RPBase')

                # Boundary the xmax as base
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[80., 0., -15.]), name='RPXmax')
                self.add_fea_interface(self.CoupleInterface(rp_name='RPXmax', instance_name='final_model', set_nodes_name='nodes_xmax'))

                # Symmetry boundary condition at the middle plane (y=0)
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='all', index_dof=[1]), name='BC_Symmetry')

                # Rigid cylinder
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[65., 0., 15.]), name='RPCylinder')
                self.add_fea_interface(self.CoupleInterface(rp_name='RPCylinder', instance_name='cylinder', set_nodes_name='cylinder'))
                self.add_fea_interface(self.BoundaryConditionRPInterface(rp_name='RPCylinder', index_dof=[0, 1, 3, 4, 5]), name='BC_RPCylinder')
                self.add_fea_interface(self.PenaltyDoFInterface(obj_name='RPCylinder', s=2), name='Penalty_RPCylinder')

                # Contact between the cylinder and the gripper
                self.add_fea_interface(self.ContactInterface(instance_name1='final_model', surface_name1='surface_zmax', instance_name2='cylinder', surface_name2='extern'), name='Contact_Gripper_Cylinder')


            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(step_index=0, load_name='Penalty_RPCylinder', values=[4e1, -10.])

        class MaterialParams(morphopt.simp.SIMP_BSPFieldMaterials):
            
            def __init__(self):
                super().__init__(mumax=mumax, 
                                 kappamax=mumax*10, 
                                 density=1.08e-9, 
                                 initial_ratio=2.,
                                 simp_ratio_min=minratio, 
                                 bounding_box=[0., 80., -1., 1., -30., 0.], 
                                 simp_field_resolution=1.0, 
                                 degree=2,
                                 voidpenalfactor=0e-2,
                                 elementname='C3D8')
            
            def reinitialize(self, iteration, *args, **kwargs):
                cps_reshaped = self._cps.reshape(self._bsp_size[0], self._bsp_size[1], self._bsp_size[2])

                cps_reshaped[:, :, -2:] = 15.

                self._cps = cps_reshaped.reshape_as(self._cps)

                super().reinitialize(iteration, *args, **kwargs)

            def get_meshes(self):
                xmin, xmax, ymin, ymax, zmin, zmax = self._bounding_box
                nx, ny, nz = self._bsp_size
                import numpy as np
                import pyvista as pv
                # Sample at the BSP control-point resolution × 2 for smooth rendering
                nx_q = max(2, (nx - 1) * 2 + 1)
                ny_q = 1
                nz_q = max(2, (nz - 1) * 2 + 1)

                xq = np.linspace(xmin, xmax, nx_q)
                yq = np.array([0.])
                zq = np.linspace(zmin, zmax, nz_q)
                xg, yg, zg = np.meshgrid(xq, yq, zq, indexing="ij")
                pts_query = np.stack([xg, yg, zg], axis=-1).reshape(-1, 3)

                designfield = self._map_bsp_designfield(
                    torch.from_numpy(pts_query).to(torch.get_default_device()).to(torch.get_default_dtype())
                )
                ratio_query = self.get_material_ratio(designfield).reshape(nx_q, ny_q, nz_q).cpu().numpy()
                ratio_grid = np.clip(ratio_query, 0.0, 1.0)

                spacing = (
                    (xmax - xmin) / max(nx_q - 1, 1),
                    (ymax - ymin) / max(ny_q - 1, 1),
                    (zmax - zmin) / max(nz_q - 1, 1),
                )
                grid = pv.ImageData(
                    dimensions=(nx_q, ny_q, nz_q),
                    spacing=spacing,
                    origin=(xmin, ymin, zmin),
                )
                grid.point_data["density"] = ratio_grid.flatten(order="F") * self._mumax

                return [grid]
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(morphopt.simp.SIMPSolver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.simp.Params):

            super().__init__(params=params,
                             available_gpus=['cuda:0'],
                            num_process=1)

    class Updater(morphopt.simp.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: morphopt.simp.Params, *args, **kwargs):
            super().__init__(materials=self.UpdaterMaterials(params=params),
                             device='cpu',
                            *args, **kwargs)

        class UpdaterMaterials(morphopt.simp.UpdaterMaterials):
            """
            Material updater based on SIMP control points.
            """

            def __init__(self, params: morphopt.simp.Params):
                super().__init__(
                    params=params,
                    max_step_iter=100,
                )

                shape_derivative = self.objectivefuncs.Sensitivity(normalize_gradient=False)
                self.add_objective_function(shape_derivative)

                # density_regularization = self.objectivefuncs.DensityFieldMinimize(scale=1e-7)
                # self.add_objective_function(density_regularization)

                # Keep SIMP control points within [0, 1] and avoid singular material values.
                self.add_constraints(self.objectivefuncs.boundarys.MinValue(xmin=-15, threshold=0.0, p=2))
                self.add_constraints(self.objectivefuncs.boundarys.MaxValue(xmax=15, threshold=0.0, p=2))

                self.add_constraints(self.objectivefuncs.VolFrac(volfrac_min=0.4, volfrac_max=0.6, penalty=1e6, element_name='C3D8'))

                self.if_update = True
    
if __name__ == '__main__':

    morphopt.start_optimization(device='cpu', restart_per_iteration=20)
