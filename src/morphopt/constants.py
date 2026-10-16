"""Central UI and kernel defaults as statically discoverable constants."""

from __future__ import annotations


class _Constants:
    FORMAT_VERSION = 1

    class UI:
        class APPLICATION:
            class STATUS_MESSAGE_DURATION_MS:
                SHORT = 3000
                LONG = 4000

        class TIMING:
            REFRESH_DEBOUNCE_MS = 250
            DEFERRED_UI_REFRESH_MS = 0

        class HISTORY:
            MAX_NODES = 100
            MAX_SNAPSHOT_BYTES = 67108864

        class OBSERVER:
            OUTPUT_MAXIMUM_BLOCKS = 10000
            POLL_INTERVAL_MS = 1000

        class UPDATER_EDITOR:
            DEFAULT_MAX_STEP_ITERATIONS = 50
            DEFAULT_INTER_SURFACE_DISTANCE = 2.5

        class WIDGETS:
            MINIMUM_LOAD_STEPS = 1
            MAXIMUM_LOAD_STEPS = 200
            MAXIMUM_QUICKSTART_OBJECTIVES = 8
            MODEL_SCAN_DEBOUNCE_MS = 500

        class MODEL_SUMMARY:
            CACHE_ENTRIES = 16

        class SCHEMA_FIELDS:

            class CAD_OPERATIONS:

                class BOX:

                    class X:
                        DEFAULT = 0.0

                    class Y:
                        DEFAULT = 0.0

                    class Z:
                        DEFAULT = 0.0

                    class DX:
                        DEFAULT = 20.0

                    class DY:
                        DEFAULT = 10.0

                    class DZ:
                        DEFAULT = 5.0

                class WEDGE:

                    class X:
                        DEFAULT = 0.0

                    class Y:
                        DEFAULT = 0.0

                    class Z:
                        DEFAULT = 0.0

                    class DX:
                        DEFAULT = 20.0

                    class DY:
                        DEFAULT = 10.0

                    class DZ:
                        DEFAULT = 5.0

                    class LTX:
                        DEFAULT = 0.0

                class CYLINDER:

                    class X:
                        DEFAULT = 0.0

                    class Y:
                        DEFAULT = 0.0

                    class Z:
                        DEFAULT = 0.0

                    class DX:
                        DEFAULT = 0.0

                    class DY:
                        DEFAULT = 0.0

                    class DZ:
                        DEFAULT = 20.0

                    class RADIUS:
                        DEFAULT = 5.0

                class SPHERE:

                    class X:
                        DEFAULT = 0.0

                    class Y:
                        DEFAULT = 0.0

                    class Z:
                        DEFAULT = 0.0

                    class RADIUS:
                        DEFAULT = 5.0

                class CONE:

                    class X:
                        DEFAULT = 0.0

                    class Y:
                        DEFAULT = 0.0

                    class Z:
                        DEFAULT = 0.0

                    class DX:
                        DEFAULT = 0.0

                    class DY:
                        DEFAULT = 0.0

                    class DZ:
                        DEFAULT = 20.0

                    class RADIUS1:
                        DEFAULT = 5.0

                    class RADIUS2:
                        DEFAULT = 1.0

                class TORUS:

                    class X:
                        DEFAULT = 0.0

                    class Y:
                        DEFAULT = 0.0

                    class Z:
                        DEFAULT = 0.0

                    class MAJOR_RADIUS:
                        DEFAULT = 8.0

                    class MINOR_RADIUS:
                        DEFAULT = 2.0

                class STEPIMPORT:

                    class FILENAME:
                        DEFAULT = ''

                    class DATA:
                        DEFAULT = ''

                class FUSE:

                    class OBJECT_ID:
                        DEFAULT = ''

                    class TOOL_ID:
                        DEFAULT = ''

                class CUT:

                    class OBJECT_ID:
                        DEFAULT = ''

                    class TOOL_ID:
                        DEFAULT = ''

                class INTERSECT:

                    class OBJECT_ID:
                        DEFAULT = ''

                    class TOOL_ID:
                        DEFAULT = ''

                class FRAGMENT:

                    class OBJECT_ID:
                        DEFAULT = ''

                    class TOOL_ID:
                        DEFAULT = ''

                class TRANSLATE:

                    class INPUT_ID:
                        DEFAULT = ''

                    class DX:
                        DEFAULT = 5.0

                    class DY:
                        DEFAULT = 0.0

                    class DZ:
                        DEFAULT = 0.0

                class ROTATE:

                    class INPUT_ID:
                        DEFAULT = ''

                    class X:
                        DEFAULT = 0.0

                    class Y:
                        DEFAULT = 0.0

                    class Z:
                        DEFAULT = 0.0

                    class AX:
                        DEFAULT = 0.0

                    class AY:
                        DEFAULT = 0.0

                    class AZ:
                        DEFAULT = 1.0

                    class ANGLE:
                        DEFAULT = 1.5707963267948966

                class DILATE:

                    class INPUT_ID:
                        DEFAULT = ''

                    class X:
                        DEFAULT = 0.0

                    class Y:
                        DEFAULT = 0.0

                    class Z:
                        DEFAULT = 0.0

                    class SX:
                        DEFAULT = 1.0

                    class SY:
                        DEFAULT = 1.0

                    class SZ:
                        DEFAULT = 1.0

                class MIRROR:

                    class INPUT_ID:
                        DEFAULT = ''

                    class A:
                        DEFAULT = 1.0

                    class B:
                        DEFAULT = 0.0

                    class C:
                        DEFAULT = 0.0

                    class D:
                        DEFAULT = 0.0

            class FEA_COMPONENTS:

                class PRESSURE:

                    class INSTANCE_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class SURFACE_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                class CONCENTRATEDFORCE:

                    class RP_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                class CONCENTRATEDMOMENT:

                    class RP_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                class BODYFORCE:

                    class ELEMENT_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class INSTANCE_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                class SPRINGTOGROUND:

                    class RP_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                class SPRINGBETWEENRPS:

                    class RP_NAME1:
                        DEFAULT = ''
                        CHOICES = ()

                    class RP_NAME2:
                        DEFAULT = ''
                        CHOICES = ()

                class PENALTYDOF:

                    class OBJ_NAME:
                        DEFAULT = ''

                    class S:
                        DEFAULT = 0

                    class OBJ_TYPE:
                        DEFAULT = 'auto'
                        CHOICES = ('auto', 'instance', 'rp', 'load', 'constraint', 'boundary')

                class BOUNDARYCONDITION:

                    class INSTANCE_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class SET_NODES_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class INDEX_DOF:
                        DEFAULT = (0, 1, 2)
                        SIZE = 6

                class BOUNDARYCONDITIONRP:

                    class RP_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class INDEX_DOF:
                        DEFAULT = (0, 1, 2)
                        SIZE = 6

                class COUPLE:

                    class RP_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class INSTANCE_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class SET_NODES_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                class REFERENCEPOINT:

                    class RP_LOCATION:
                        DEFAULT = (0.0, 0.0, 0.0)

                class CONTACT:

                    class INSTANCE_NAME1:
                        DEFAULT = ''
                        CHOICES = ()

                    class SURFACE_NAME1:
                        DEFAULT = ''
                        CHOICES = ()

                    class INSTANCE_NAME2:
                        DEFAULT = ''
                        CHOICES = ()

                    class SURFACE_NAME2:
                        DEFAULT = ''
                        CHOICES = ()

                    class PENALTY_THRESHOLD_H:
                        DEFAULT = 3.0

                class CONTACTSELF:

                    class INSTANCE_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class SURFACE_NAME:
                        DEFAULT = ''
                        CHOICES = ()

            class SURFACES:

                class BSP_CYLINDER:

                    class R0:
                        DEFAULT = 4.0
                        MIN = 0.0

                    class LENGTH:
                        DEFAULT = 74.0
                        MIN = 0.0

                    class SEED_SIZE:
                        DEFAULT = 1.0
                        MIN = 0.0001

                    class NUM_U_RATIO:
                        DEFAULT = 1
                        MIN = 1

                    class NUM_V_RATIO:
                        DEFAULT = 1
                        MIN = 1

                    class DEGREE:
                        DEFAULT = 3
                        MIN = 1

                    class INIT_LOCATION:
                        DEFAULT = (0.0, 0.0, 0.0)

                    class MAXR:
                        DEFAULT = 0.2
                        MIN = 0.0

                    class MAXC:
                        DEFAULT = 1.0
                        MIN = 0.0

                    class MAXFF:
                        DEFAULT = 0.2
                        MIN = 0.0

                    class PERTURBATION_L:
                        DEFAULT = -1.0

                class CPGEO_CYLINDER:

                    class R0:
                        DEFAULT = 4.0
                        MIN = 0.0

                    class LENGTH:
                        DEFAULT = 74.0
                        MIN = 0.0

                    class SEED_SIZE:
                        DEFAULT = 1.0
                        MIN = 0.0001

                    class NUM_U_RATIO:
                        DEFAULT = 1
                        MIN = 1

                    class NUM_V_RATIO:
                        DEFAULT = 1
                        MIN = 1

                    class INIT_LOCATION:
                        DEFAULT = (0.0, 0.0, 0.0)

                    class MAXC:
                        DEFAULT = 1.0
                        MIN = 0.0

                    class PERTURBATION_L:
                        DEFAULT = -1.0

                class CPGEO_SPHERE:

                    class R0:
                        DEFAULT = 7.0
                        MIN = 0.0

                    class SEED_SIZE:
                        DEFAULT = 1.5
                        MIN = 0.0001

                    class INIT_LOCATION:
                        DEFAULT = (0.0, 0.0, 0.0)

                    class MAXC:
                        DEFAULT = 1.0
                        MIN = 0.0

                class FIXED_STL:

                    class PATH_STL:
                        DEFAULT = ''

            class MATERIALS:

                class HOMOGENEOUSMATERIAL:

                    class PART_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class MATERIAL_MODEL:
                        DEFAULT = 'NeoHookeanLnJ'
                        CHOICES = ('LinearElastic',
                                   'NeoHookean',
                                   'NeoHookeanLnJ',
                                   'MooneyRivlin',
                                   'Yeoh',
                                   'Gent',
                                   'ArrudaBoyce',
                                   'Ogden')

                    class E:
                        DEFAULT = 1.0

                    class NU:
                        DEFAULT = 0.45

                    class MU:
                        DEFAULT = 0.482

                    class KAPPA:
                        DEFAULT = 4.8

                    class C10:
                        DEFAULT = 0.241

                    class C01:
                        DEFAULT = 0.241

                    class C1:
                        DEFAULT = 0.482

                    class C2:
                        DEFAULT = 0.0

                    class C3:
                        DEFAULT = 0.0

                    class JM:
                        DEFAULT = 100.0

                    class N:
                        DEFAULT = 10.0

                    class ALPHA:
                        DEFAULT = (2.0,)

                    class DENSITY:
                        DEFAULT = 1.08e-09

                    class ELEMENTNAME:
                        DEFAULT = ''
                        CHOICES = ('',)

                class SIMP_BSPFIELDMATERIALS:

                    class PART_NAME:
                        DEFAULT = ''
                        CHOICES = ()

                    class MATERIAL_MODEL:
                        DEFAULT = 'NeoHookeanLnJ'
                        CHOICES = ('LinearElastic',
                                   'NeoHookean',
                                   'NeoHookeanLnJ',
                                   'MooneyRivlin',
                                   'Yeoh',
                                   'Gent',
                                   'ArrudaBoyce',
                                   'Ogden')

                    class MUMAX:
                        DEFAULT = 10.0

                    class KAPPAMAX:
                        DEFAULT = 100.0

                    class E:
                        DEFAULT = 1.0

                    class NU:
                        DEFAULT = 0.45

                    class MU:
                        DEFAULT = 0.482

                    class KAPPA:
                        DEFAULT = 4.8

                    class C10:
                        DEFAULT = 0.241

                    class C01:
                        DEFAULT = 0.241

                    class C1:
                        DEFAULT = 0.482

                    class C2:
                        DEFAULT = 0.0

                    class C3:
                        DEFAULT = 0.0

                    class JM:
                        DEFAULT = 100.0

                    class N:
                        DEFAULT = 10.0

                    class ALPHA:
                        DEFAULT = (2.0,)

                    class SIMP_RATIO_MIN:
                        DEFAULT = 1e-07

                    class BOUNDING_BOX:
                        DEFAULT = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

                    class SIMP_FIELD_RESOLUTION:
                        DEFAULT = 0.5

                    class DEGREE:
                        DEFAULT = 2

                    class DENSITY:
                        DEFAULT = 1.08e-09

                    class INITIAL_RATIO:
                        DEFAULT = 0.5

                    class VOIDPENALFACTOR:
                        DEFAULT = 0.01

                    class MATERIALPENALTY:
                        DEFAULT = 8

                    class ELEMENTNAME:
                        DEFAULT = ''
                        CHOICES = ('',)

            class PARTS:

                class BOUNDARYPART:

                    class FEA_SEED_SIZE:
                        DEFAULT = 2.5
                        MIN = 0.001

                    class MESH_ORDER:
                        DEFAULT = 1
                        CHOICES = (1, 2)

                    class EXTERIOR_SURFACE:
                        DEFAULT = 'surface_0_All'

                    class PART_NAME:
                        DEFAULT = ''

                class INPPART:

                    class MESH_FILE:
                        DEFAULT = ''

                    class INP_PART_NAME:
                        DEFAULT = ''

                    class EXTERIOR_SURFACE:
                        DEFAULT = ''

                    class PART_NAME:
                        DEFAULT = ''

                class TORCHFEAPART:

                    class MODEL_DIRECTORY:
                        DEFAULT = ''

                    class MODEL_FILENAME:
                        DEFAULT = ''

                    class MODEL_PART_NAME:
                        DEFAULT = ''

                    class EXTERIOR_SURFACE:
                        DEFAULT = ''

                    class PART_NAME:
                        DEFAULT = ''

                class BASEPART:

                    class EXTERIOR_SURFACE:
                        DEFAULT = ''

                    class PART_NAME:
                        DEFAULT = ''

                class BOXPART:

                    class LENGTH:
                        DEFAULT = 40.0
                        MIN = 0.001

                    class HEIGHT:
                        DEFAULT = 16.0
                        MIN = 0.001

                    class DEPTH:
                        DEFAULT = 8.0
                        MIN = 0.001

                    class MESH_SIZE:
                        DEFAULT = 2.0
                        MIN = 0.001

                    class MESH_ORDER:
                        DEFAULT = 2
                        CHOICES = (1, 2)

                    class EXTERIOR_SURFACE:
                        DEFAULT = 'extern'

                    class PART_NAME:
                        DEFAULT = ''

                class CADPART:

                    class MESH_SIZE:
                        DEFAULT = 2.0
                        MIN = 0.001

                    class MESH_ORDER:
                        DEFAULT = 1
                        CHOICES = (1, 2)

                    class EXTERIOR_SURFACE:
                        DEFAULT = 'extern'

                    class PART_NAME:
                        DEFAULT = ''

                class OFFSETBOUNDARYPART:

                    class FEA_SEED_SIZE:
                        DEFAULT = 2.5
                        MIN = 0.001

                    class MESH_ORDER:
                        DEFAULT = 1
                        CHOICES = (1, 2)

                    class EXTERIOR_SURFACE:
                        DEFAULT = 'surface_0_All'

                    class PART_NAME:
                        DEFAULT = ''

                    class SHELL_THICKNESS:
                        DEFAULT = 0.5
                        MIN = 0.001

                    class NUM_LAYERS:
                        DEFAULT = 1
                        MIN = 1

            class SURFACE_CONSTRAINTS:

                class BSPMIRROR:

                    class PLANE:
                        DEFAULT = 'xz'
                        CHOICES = ('xz', 'xy')

                    class OFFSET:
                        DEFAULT = 0.0

                class CPGEOMIRROR:

                    class PLANE:
                        DEFAULT = 'xz'
                        CHOICES = ('xy', 'xz', 'yz')

                    class OFFSET:
                        DEFAULT = 0.0

                class CPGEOROTATION:

                    class AXIS:
                        DEFAULT = 'z'
                        CHOICES = ('x', 'y', 'z')

                    class ORDER:
                        DEFAULT = 2
                        MIN = 2

                    class CENTER:
                        DEFAULT = (0.0, 0.0, 0.0)

                class BSPRELATION:

                    class POSE:
                        DEFAULT = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

                class CPGEORELATION:

                    class POSE:
                        DEFAULT = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

                class CUSTOM:

                    class CODE:
                        DEFAULT = ''

            class UPDATER_OBJECTIVES:

                class SENSITIVITY:

                    class NORMALIZE_GRADIENT:
                        DEFAULT = False

                class DENSITYFIELDMINIMIZE:

                    class SCALE:
                        DEFAULT = 1e-07

            class UPDATER_CONSTRAINTS:

                class DISTANCE:

                    class MIN_DISTANCE:
                        DEFAULT = ((2.5, 2.5), (2.5, 2.5))

                class CYLINDER:

                    class RADIUS:
                        DEFAULT = 10.0

                    class HEIGHT:
                        DEFAULT = 80.0

                    class BOTTOM:
                        DEFAULT = 0.0

                class MINRADIUS:

                    class RADIUS:
                        DEFAULT = 2.0

                class VOLUMEMAXIMIZATION:

                    class SURF_IDX:
                        DEFAULT = 1
                        MIN = 1

                    class WEIGHT:
                        DEFAULT = 0.01

                class INWARDCURVATURERADIUS:

                    class MARGIN:
                        DEFAULT = 0.4

                    class MARGIN_RATIO:
                        DEFAULT = 0.45

                    class P:
                        DEFAULT = 8
                        MIN = 1

                    class PENALTY_SCALE:
                        DEFAULT = 1000.0

                class OFFSETSURFACEMINTHICKNESS:

                    class MIN_DISTANCE:
                        DEFAULT = 2.0

                class VOLFRAC:

                    class VOLFRAC_MIN:
                        DEFAULT = 0.0

                    class VOLFRAC_MAX:
                        DEFAULT = 0.6

                    class PENALTY:
                        DEFAULT = 10000.0

                    class ELEMENTNAME:
                        DEFAULT = ''
                        CHOICES = ()

                class MINVALUE:

                    class XMIN:
                        DEFAULT = -15.0

                    class THRESHOLD:
                        DEFAULT = 0.0

                    class P:
                        DEFAULT = 2
                        MIN = 1

                class MAXVALUE:

                    class XMAX:
                        DEFAULT = 15.0

                    class THRESHOLD:
                        DEFAULT = 0.0

                    class P:
                        DEFAULT = 2
                        MIN = 1
        class MATERIAL_MODEL_DEFAULTS:
            E = 1.0
            NU = 0.45
            MU = 0.482
            KAPPA = 4.8
            C10 = 0.241
            C01 = 0.241
            C1 = 0.482
            C2 = 0.0
            C3 = 0.0
            JM = 100.0
            N = 10.0
            ALPHA = (2.0,)

        class QUICKSTART:
            class DEFAULT:
                LENGTH = 80.0
                BODY_RADIUS = 10.0
                OBJECTIVE_WEIGHT = 1.0
                GEOMETRY_MAX_STEP_ITERATIONS = 50
                NUM_PROCESS = 1
                WALL = 2.0
                MESH_SIZE = 2.0
                MATERIAL_MU = 0.482
                MATERIAL_KAPPA = 4.8
                OBJECTIVE_TARGET = 20.0
                WORKSPACE_PRESSURE_KPA = 60.0
                WORKSPACE_CHANNELS = (1, 2)
                PRESSURES_KPA = (60.0, 0.0)
                GAUSS_ORDER = 3
                FORCE_N = 1.0
                SIMP_LENGTH = 40.0
                SIMP_MU = 10.0
                SIMP_KAPPA = 100.0
                BOX_HEIGHT = 16.0
                BOX_DEPTH = 8.0
                VOLUME_FRACTION = 0.4

            class DEFAULT_LAYER:
                LENGTH = 80.0
                CHAMBERS = 2
                ARRANGEMENT = "ring"
                RADIUS = 2.0
                CENTER_RADIUS = 5.0
                SHAPE = "cylinder"
                PHASE_DEGREES = 180.0
                PRESSURE_CHANNELS = (1, 2)

            class GENERATION:
                SHAPE_SEED_RADIUS_DIVISOR = 2.0
                SHAPE_SEED_LENGTH_DIVISOR = 12.0
                CONTACT_OBJECT_Z_FRACTION = 0.7
                CONTACT_WALL_THRESHOLD_DIVISOR = 2.0
                SIMP_FIELD_RESOLUTION_DIVISOR = 2.0
                SIMP_DEGREE = 2
                SIMP_VARIABLE_BOUNDS = (-15.0, 15.0)
                SIMP_VOLUME_FRACTION_PENALTY = 1000000.0

            class LIMITS:
                OBJECTIVE_MIN_COUNT = 1
                OBJECTIVE_MAX_COUNT = 8
                LAYER_MIN_COUNT = 1
                LAYER_MAX_COUNT = 8
                CHAMBER_MAX_COUNT = 8
                WORKSPACE_GAUSS_ORDER_MIN = 1
                WORKSPACE_GAUSS_ORDER_MAX = 8
                SIMP_MAX_ELEMENT_COUNT = 100000
                MINIMUM_LAYER_LENGTH_WALL_RATIO = 4.0
                GEOMETRY_CLEARANCE_TOLERANCE = 1e-09

            class WIDGET:
                LAYER_ADDED_LENGTH = 40.0
                PRESSURE_MAX_KPA = 1000.0
                PRESSURE_DECIMALS = 1
                OBJECTIVE_WEIGHT_MAXIMUM = 1000.0
                OBJECTIVE_WEIGHT_DECIMALS = 3
                OBJECTIVE_TARGET_MINIMUM = 0.001
                OBJECTIVE_TARGET_MAXIMUM = 10000.0
                OBJECTIVE_TARGET_DECIMALS = 2
                FORCE_MINIMUM = 0.001
                FORCE_MAXIMUM = 1000.0
                FORCE_DECIMALS = 2
                WORKSPACE_PRESSURE_MINIMUM = 0.1
                WORKSPACE_PRESSURE_MAXIMUM = 1000.0
                WORKSPACE_PRESSURE_DECIMALS = 1
                SHAPE_LENGTH_MAXIMUM = 1000000000000.0
                TOPOLOGY_LENGTH_MAXIMUM = 1000.0

                class NUMERIC_FIELD_DECIMALS:
                    DEFAULT = 1
                    MATERIAL = 3
                    VOLUME_FRACTION = 2

                class NUMERIC_FIELD_STEP:
                    GEOMETRY = 0.1
                    LENGTH = 5.0
                    PRESSURE_KPA = 5.0
                    VOLUME_FRACTION = 0.05

                class FIELDS:
                    class LENGTH:
                        RANGE = (5.0, 1000.0)

                    class RADIUS:
                        RANGE = (1.0, 200.0)

                    class WALL:
                        RANGE = (0.2, 30.0)

                    class HEIGHT:
                        RANGE = (1.0, 300.0)

                    class DEPTH:
                        RANGE = (1.0, 100.0)

                    class MESH_SIZE:
                        RANGE = (0.2, 10.0)

                    class MU:
                        RANGE = (0.001, 1000.0)

                    class KAPPA:
                        RANGE = (0.001, 10000.0)

                    class VOLUME_FRACTION:
                        RANGE = (0.05, 0.95)

        class OBJECTIVE:
            TYPE_DISPLACEMENT = "displacement"
            TYPE_CUSTOM_LOSS = "custom_loss"
            DEFAULT_TYPE = TYPE_DISPLACEMENT
            DIRECTION_TARGET = "target"
            DIRECTION_MAXIMIZE = "maximize"
            DIRECTION_MINIMIZE = "minimize"
            DEFAULT_DIRECTION = DIRECTION_TARGET
            DISPLACEMENT_COMPONENTS = (
                ("ux", 0),
                ("uy", 1),
                ("uz", 2),
                ("rx", 3),
                ("ry", 4),
                ("rz", 5),
            )
            DEFAULT_TARGET = 0.0
            DEFAULT_WEIGHT = 1.0
            TARGET_MINIMUM = -1000000.0
            TARGET_MAXIMUM = 1000000.0
            WEIGHT_MINIMUM = 0.0
            WEIGHT_MAXIMUM = 1000000.0
            FIELD_DECIMALS = 6

        class METRIC:
            TYPE_DISPLACEMENT = "displacement"
            TYPE_CUSTOM = "custom"
            DEFAULT_TYPE = TYPE_DISPLACEMENT

    class KERNEL:
        class CONTROLLER:
            RESTART_PER_ITERATION = 20

        class SOLVER:
            NUM_PROCESS = 4
            STATIC_TOLERANCE_ERROR = 1e-07

        class VISUALIZATION:
            WINDOW_SIZE = (1200, 1200)
            CAMERA_AZIMUTH_DEGREES = 210
            CAMERA_ELEVATION_DEGREES = 20
            INSTANCE_COLORS = ("#2878b5", "#edb120", "#af52cd", "#f15854", "#779548")
            SIMP_WINDOW_SIZE = (1400, 1000)
            SIMP_DENSITY_THRESHOLD_RATIO = 0.5
            class SIMP_DENSITY_HISTOGRAM:
                FIGURE_SIZE = (8, 5)
                BINS = 50
                COLOR = "C0"
                BAR_OPACITY = 0.8
                GRID_OPACITY = 0.4
                DPI = 300
            BOUNDARY_OUTER_SURFACE_OPACITY = 0.6
            BOUNDARY_DIFFUSE = 0.8
            BOUNDARY_SPECULAR = 0.2
            BOUNDARY_AMBIENT = 0.3
            BOUNDARY_SPECULAR_POWER = 10
            OFFSET_SHELL_SURFACE_OPACITY = 1.0

        class MESH:
            SURFACE_ELEMENT_LINE_CHUNK_SIZE = 16
            SURFACE_NODE_LINE_CHUNK_SIZE = 16
            MAXIMUM_SIZE_RATIO = 1.0
            MINIMUM_SIZE_RATIO = 0.5
            DEFAULT_CAD_MESH_SIZE = 1.0
            DEFAULT_BOUNDARY_SEED_SIZE = 1.0
            DEFAULT_ELEMENT_ORDER = 1

        class FEA:
            DEFAULT_TRANSLATION_DOFS = (0, 1, 2)
            CONTACT_PENALTY_THRESHOLD = 3.0

        class MATERIAL:
            DEFAULT_DENSITY = 0.0

        class BOUNDARY_PART:
            NODE_SET_TOLERANCE = 0.001
            UPDATE_STEP_EPSILON = 1e-15

        class SHAPE_OBJECTIVES:
            DEFAULT_WEIGHT = 1.0

        class SHAPE_CONSTRAINTS:
            BARRIER_THRESHOLD = 0.05
            BARRIER_RATIO = 0.0
            MIN_RADIUS_EXPONENT = 3
            CYLINDER_EXPONENT = 7
            DISTANCE_SEARCH_RATIO = 1.5
            DISTANCE_PAIR_PRUNE_RATIO = 0.3
            DISTANCE_BARRIER_THRESHOLD = 0.01
            DISTANCE_BARRIER_EXPONENT = 5
            NORMAL_TRANSITION_MIN = -0.7
            NORMAL_TRANSITION_MAX = 0.0
            NORMALIZATION_TOLERANCE = 1e-08

        class SIMP_CONSTRAINTS:
            BARRIER_THRESHOLD = 0.05
            BARRIER_RATIO = 0.0
            MINIMUM_THRESHOLD = 1e-12
            DENSITY_FIELD_MINIMIZE_SCALE = 1e-07
            MINIMUM_VALUE = 0.0
            MAXIMUM_VALUE = 1.0
            DEFAULT_THRESHOLD = 0.0
            DEFAULT_EXPONENT = 3

        class CODESIGN_GEOMETRY:
            DEFAULT_SHELL_THICKNESS = 1.0

        class OPTIMIZER:
            LINE_SEARCH_C1 = 0.0001
            LINE_SEARCH_BACKTRACK_RATIO = 0.2
            LINE_SEARCH_MIN_STEP_TOLERANCE = 1e-14
            LBFGS_MEMORY_PAIRS = 10
            LBFGS_CONVERGENCE_TOLERANCE = 1e-10
            LBFGS_CURVATURE_TOLERANCE = 1e-14
            LBFGS_SHAPE_MEMORY_PAIRS = 20
            LBFGS_MATERIAL_MEMORY_PAIRS = 20

        class SHAPE_UPDATE:
            MAX_STEP_ITERATIONS = 100
            MAX_STEP_LENGTH = 0.5
            INITIAL_STEP_LENGTH_RATIO = 0.5
            DIRECTION_CHANGE_THRESHOLD = -0.5
            MIN_STEP_LENGTH_RATIO = 0.1
            STEP_LENGTH_DECAY = 0.5
            STEP_LENGTH_INCREASE = 1.5
            LOW_STEP_LENGTH_TOLERANCE = 1e-10
            LOW_STEP_LENGTH_ITERATION_LIMIT = 10
            STATUS_LOG_INTERVAL = 10
            LINE_SEARCH_ITERATIONS = 20
            LINE_SEARCH_TOLERANCE = 1e-10

        class SIMP_UPDATE:
            MAX_STEP_ITERATIONS = 50
            MAX_STEP_LENGTH = 1.0
            INITIAL_STEP_LENGTH_RATIO = 0.5
            MIN_STEP_LENGTH_RATIO = 0.1
            STEP_LENGTH_DECAY = 0.5
            STEP_LENGTH_INCREASE = 1.5
            LOW_STEP_LENGTH_TOLERANCE = 1e-10
            LOW_STEP_LENGTH_ITERATION_LIMIT = 10
            STATUS_LOG_INTERVAL = 10
            LINE_SEARCH_ITERATIONS = 20
            LINE_SEARCH_TOLERANCE = 1e-10

        class SURFACE:
            OBJ_VERTEX_MERGE_TOLERANCE = 1e-06
            STEP_DISTANCE_ACCURACY_MM = 0.001
            DEFAULT_CURVATURE_LIMIT = 1.0
            DEFAULT_METRIC_VARIATION_LIMIT = 0.2
            DEFAULT_NONORTHOGONALITY_LIMIT = 0.2
            BSP_CLASS_NONORTHOGONALITY_LIMIT = 0.1
            FAIRNESS_ACTIVATION_RATIO = 0.8
            BSP_FAIRNESS_EXPONENT = 3
            CPGEO_FAIRNESS_EXPONENT = 5
            CYLINDER_CIRCUMFERENTIAL_BASE_SEGMENTS = 12
            CYLINDER_INITIAL_PERTURBATION_RATIO = 0.04
            FIXED_END_CONTROL_POINT_ROWS = 5
            BSP_BOUNDARY_SUBDIVISION_RATIO = 2
            CPGEO_INITIAL_REFINEMENT_ITERATIONS = 4
            CPGEO_OUTPUT_REFINEMENT_ITERATIONS = 2
            CPGEO_KNOT_INFLUENCE_COUNT = 20
            CPGEO_AREA_IMBALANCE_THRESHOLD = 5.0
            SPHERE_POLE_OFFSET = 1e-09
            BSP_PROJECTION_SUBDIVISION_RATIO = 2
            PROJECTION_ITERATIONS_BSP = 10
            PROJECTION_ITERATIONS_CPGEO = 5
            PROJECTION_TOLERANCE = 0.01
            PROJECTION_BATCH_SIZE_BSP = 40960
            PROJECTION_BATCH_SIZE_CPGEO = 4096
            PROJECTION_NODE_CHUNK_SIZE = 1024
            PROJECTION_REGULARIZATION_TOLERANCE = 1e-12
            PROJECTION_LINE_SEARCH_STEPS = 7
            PROJECTION_LINE_SEARCH_DECAY = 0.5
            PROJECTION_PARAMETER_MIN = 0.0
            PROJECTION_PARAMETER_MAX = 1.0

        class SIMP:
            DEFAULT_INITIAL_RATIO = 0.5
            DEFAULT_VOID_PENALTY_FACTOR = 0.01
            DEFAULT_MATERIAL_PENALTY = 8
            DENSITY_FLOOR = 1e-06
            INITIAL_VARIABLE_NOISE = 1e-06

        class CODESIGN:
            CURVATURE_MARGIN = 0.4
            CURVATURE_MARGIN_RATIO = 0.45
            CURVATURE_BARRIER_THRESHOLD_RATIO = 0.1
            THICKNESS_SEARCH_RATIO = 1.5
            THICKNESS_BARRIER_THRESHOLD_RATIO = 0.05
            BARRIER_EXPONENT = 8
            PENALTY_SCALE = 1000.0
            HARD_VIOLATION_BETA = 8.0
            GEOMETRY_TOLERANCE = 1e-12
            DISTANCE_SQUARED_TOLERANCE = 1e-18
            HARD_VIOLATION_EXPONENT_MAX = 20.0
            NORMAL_TRANSITION_MIN = -0.7
            NORMAL_TRANSITION_MAX = -0.5
            BARRIER_PENALTY_RATIO = 0.0
            NORMAL_OPPOSITION_THRESHOLD = 0.0


CONSTANT: _Constants = _Constants()
