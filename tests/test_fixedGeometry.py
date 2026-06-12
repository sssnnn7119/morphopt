import torchfea

import morphopt


if __name__ == "__main__":
    class GeometryParams(morphopt.simp.FixedGeometry):

        def define_assembly(self):
            part = torchfea.cad.create_box(xmin=0.0, xmax=80.0, ymin=-10.0, ymax=0.0, zmin=-30.0, zmax=0.0, nx=80, ny=10, nz=30, element_name='C3D8')
            assembly = torchfea.Assembly()
            assembly.add_part(part=part, name='final_model')
            return assembly

    params = GeometryParams()
    params.initialize()

    part = params.assembly.get_part('final_model')

    part.surfaces.initialize(part)

    part.get_mesh().plot()

    assembly = params.assembly