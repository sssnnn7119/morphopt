"""Central UI and kernel defaults as statically discoverable constants."""

from __future__ import annotations


class _Constants:
    FORMAT_VERSION = 1

    class UI:
        class APPLICATION:
            MAIN_WINDOW_SIZE = (1500, 880)

            class STATUS_MESSAGE_DURATION_MS:
                SHORT = 3000
                LONG = 4000

        class LAYOUT:
            class WORKBENCH:
                OUTPUT_NAME_WIDTH = 180
                PATH_MINIMUM_WIDTH = 120
                DIRECTORY_BUTTON_WIDTH = 30
                DEVICE_SELECTOR_WIDTH = 150
                LEFT_MINIMUM_WIDTH = 230
                EDITOR_MINIMUM_WIDTH = 440
                LEFT_SPLIT_SIZES = (500, 260)
                MAIN_SPLIT_SIZES = (230, 560, 460)
                DESCRIPTION_MARGINS = (16, 16, 16, 16)

            class HISTORY:
                ROW_HEIGHT = 28
                GRAPH_LEFT_MARGIN = 12
                GRAPH_RIGHT_MARGIN = 14
                GRAPH_TEXT_GAP = 6
                GRAPH_LANE_SPACING = 18
                GRAPH_LINE_WIDTH = 2
                GRAPH_NODE_RADIUS = 4
                GRAPH_CURRENT_NODE_RADIUS = 5
                GRAPH_BRANCH_COLORS = (
                    "#48a9e8",
                    "#d08bda",
                    "#e3a44b",
                    "#63bd91",
                    "#dd7373",
                    "#8e9ee8",
                )

            LANGUAGE_SELECTOR_WIDTH = 110

        class TIMING:
            REFRESH_DEBOUNCE_MS = 250
            DEFERRED_UI_REFRESH_MS = 0

        class HISTORY:
            MAX_NODES = 100
            MAX_SNAPSHOT_BYTES = 67108864

        class EDITOR:
            CODE_FONT_SIZE = 10
            HELPER_CODE_MINIMUM_HEIGHT = 220

        class OBSERVER:
            STEP_BUTTON_WIDTH = 30
            ITERATION_LABEL_MINIMUM_WIDTH = 70
            OPTION_PANEL_WIDTH = 160
            OPTION_SPLIT_SIZES = (160, 1100)
            OUTPUT_MAXIMUM_BLOCKS = 10000
            CONTENT_STRETCH_FACTORS = (5, 1)
            CONTENT_SPLIT_SIZES = (700, 180)
            POLL_INTERVAL_MS = 1000
            METRICS_CHART_BACKGROUND = "#121212"
            METRICS_LINE_COLOR = "cyan"
            METRICS_LINE_WIDTH = 1.5
            METRICS_MARKER_SIZE = 5.0
            METRICS_GRID_COLOR = "white"
            METRICS_GRID_WIDTH = 0.5
            DEFORMATION_MESH_COLOR = "#2878b5"

        class UPDATER_EDITOR:
            SELECTION_SCROLL_MARGINS = (10, 10)
            SURFACE_SELECTOR_MINIMUM_WIDTH = 80
            DEFAULT_MAX_STEP_ITERATIONS = 50
            DEFAULT_INTER_SURFACE_DISTANCE = 2.5
            ITEM_BUTTON_HEIGHT = 30
            SURFACE_PANEL_MINIMUM_WIDTH = 250
            SURFACE_PANEL_MARGINS = (8, 6, 8, 6)
            SURFACE_PANEL_SPACING = 4
            SURFACE_CHECK_SPACING = 2

            class SURFACE_LIST_HEIGHT:
                MAXIMUM = 200
                BASE = 18
                ROW_HEIGHT = 26

            DISTANCE_MATRIX_BUTTON_MINIMUM_WIDTH = 110
            DISTANCE_MATRIX_PANEL_MARGINS = (8, 8, 8, 8)
            DISTANCE_MATRIX_PANEL_SPACING = 6

            class DISTANCE_MATRIX_TABLE_HEIGHT:
                MAXIMUM = 440
                BASE = 40
                ROW_HEIGHT = 30
                SECTION_HEIGHT = 26

        class WIDGETS:
            ACTION_BUTTON_HEIGHT = 30
            ITEM_ACTION_BUTTON_WIDTH = 32
            OBJECTIVE_SELECTOR_HEIGHT = 30
            MULTILINE_FIELD_MINIMUM_HEIGHT = 120
            PATH_BUTTON_WIDTH = 28
            CONTINUE_DIALOG_MINIMUM_WIDTH = 380
            SOURCE_DIALOG_MINIMUM_WIDTH = 480
            MINIMUM_LOAD_STEPS = 1
            MAXIMUM_LOAD_STEPS = 200
            MAXIMUM_QUICKSTART_OBJECTIVES = 8
            LOAD_STEP_TABLE_MINIMUM_HEIGHT = 220
            FORM_CONTENTS_MARGINS = (8, 4, 8, 4)
            COLLECTION_CONTENTS_MARGINS = (4, 4, 4, 4)
            COLLECTION_SPACING = 8
            STANDARD_FORM_SPACING = 6
            ACTION_ROW_VERTICAL_MARGIN = 2
            ACTION_GRID_COLUMNS = 2
            ACTION_GRID_SPACING = 6
            CODE_COMPLETION_MINIMUM_WIDTH = 260
            CODE_EDITOR_MINIMUM_HEIGHT = 140
            CUSTOM_CLASS_BASE_MINIMUM_WIDTH = 400
            MODEL_SUMMARY_INDENTATION = 18
            MODEL_SUMMARY_NAME_COLUMN_WIDTH = 240
            MODEL_SCAN_DEBOUNCE_MS = 500

        class MODEL_SUMMARY:
            CACHE_ENTRIES = 16

        class VIEWER:
            SCENE_FALLBACK_DIAGONAL = 10.0
            GLYPH_WIDTH_RATIO = 4.0
            BOUNDARY_SHELL_OPACITY = 0.28
            MATERIAL_REGION_OPACITY = 0.6
            MATERIAL_REGION_FILL_OPACITY = 0.03

            class GEOMETRY:
                INSTANCE_COLORS = (
                    "#71899a",
                    "#a77b6d",
                    "#6f8e83",
                    "#887e9d",
                    "#aa905f",
                    "#82916a",
                    "#a47787",
                    "#718397",
                )
                UNINSTANCED_COLOR = "#77838c"
                CYLINDER_RESOLUTION = 64
                SPHERE_THETA_RESOLUTION = 48
                SPHERE_PHI_RESOLUTION = 48
                BOUNDARY_RELATIVE_TOLERANCE = 1e-06
                BOUNDARY_ABSOLUTE_TOLERANCE = 1e-08
                ROTATION_ZERO_TOLERANCE = 1e-12
                EXTRA_INSTANCE_HUE_STEP = 0.61803398875
                EXTRA_INSTANCE_HUE_OFFSET = 0.11
                EXTRA_INSTANCE_SATURATION = 0.4
                EXTRA_INSTANCE_VALUE = 0.76
                MESH_LIGHT_DIRECTION = (1.0, -1.0, 2.0)
                MESH_LIGHT_AMBIENT = 0.65
                MESH_LIGHT_CONTRAST = 0.35
                BASE_UNINSTANCED_COLOR = "#77838c"
                CAD_FACE_AMBIENT = 0.2
                CAD_FACE_DIFFUSE = 0.72
                CAD_FACE_SPECULAR = 0.22
                CAD_FACE_SPECULAR_POWER = 28
                CAD_EDGE_COLOR = "#f5f6f8"
                CAD_EDGE_WIDTH = 2.5
                CAD_LABEL_FONT_SIZE = 14
                CAD_LABEL_SHAPE_COLOR = "#101722"
                CAD_LABEL_SHAPE_OPACITY = 0.94
                MATERIAL_REGION_COLOR = "#7f8c8d"
                MATERIAL_REGION_FILL_OPACITY = 0.03
                MATERIAL_REGION_OPACITY = 0.6
                SURFACE_NORMAL_TOLERANCE = 1e-12

            class LOADS:
                PRESSURE_ZERO_TOLERANCE = 1e-12
                PRESSURE_SURFACE_SAMPLES = 3
                PRESSURE_SURFACE_COLOR = "#38c7ce"
                PRESSURE_ARROW_COLOR = "#a8f5da"
                PRESSURE_OPACITY = 0.9
                PRESSURE_AMBIENT = 0.4
                PRESSURE_DIFFUSE = 0.6
                PRESSURE_SPECULAR = 0.15
                PRESSURE_PREVIEW_OFFSET_RATIO = 0.0015
                FORCE_COLOR = "#e74c3c"
                BODY_FORCE_COLOR = "#ff8c42"
                PENALTY_COLOR = "#ec4899"
                BOUNDARY_COLOR = "#398bd0"
                BOUNDARY_OUTLINE_COLOR = "#8bc8ff"
                BOUNDARY_MARKER_COLOR = "#4aa3df"
                BOUNDARY_OPACITY = 0.6
                BOUNDARY_PREVIEW_OFFSET_RATIO = 0.0015
                BOUNDARY_OUTLINE_WIDTH_RATIO = 0.0018
                LOAD_ARROW_LENGTH_RATIO = 0.04
                LOAD_ARROW_TIP_LENGTH_RATIO = 0.25
                LOAD_ARROW_TIP_RADIUS_RATIO = 0.055
                LOAD_ARROW_SHAFT_RADIUS_RATIO = 0.015
                COUPLING_SPOKE_COUNT = 8
                GLYPH_ZERO_TOLERANCE = 1e-12

            class RENDER:
                BACKGROUND = "#0e131c"
                DEPTH_PEELS = 8
                DEPTH_PEELING_OCCLUSION_RATIO = 0.0
                MESH_AMBIENT = 0.17
                MESH_DIFFUSE = 0.78
                MESH_SPECULAR = 0.24
                MESH_SPECULAR_POWER = 30
                LEGEND_MIN_WIDTH = 0.13
                LEGEND_MAX_WIDTH = 0.28
                LEGEND_BASE_WIDTH = 0.055
                LEGEND_NAME_WIDTH_RATIO = 0.008
                LEGEND_MAX_HEIGHT = 0.4
                LEGEND_ROW_HEIGHT = 0.025
                LEGEND_PADDING = 4
                LEGEND_BACKGROUND = "#1a202a"
                LEGEND_BACKGROUND_OPACITY = 0.8
                LEGEND_TEXT_COLOR = (0.86, 0.9, 0.95)
                LEGEND_FONT_SIZE = 10
                LABEL_FONT_SIZE = 10
                LABEL_MARGIN = 6
                LABEL_OPACITY = 0.97
                COUPLING_SURFACE_OPACITY = 0.46
                COUPLING_SURFACE_COLOR = "#dcae67"
                COUPLING_EDGE_COLOR = "#edc27e"
                COUPLING_SPOKE_COLOR = "#dfad62"
                COUPLING_LABEL_COLOR = "#edc27e"
                COUPLING_LABEL_SIDE = 1.0
                REFERENCE_POINT_LABEL_SIDE = -1.0
                ANNOTATION_TEXT_COLOR = "#dce4ee"
                ANNOTATION_BACKGROUND_COLOR = "#202833"
                ANNOTATION_LEADER_OPACITY = 0.68
                ANNOTATION_LEADER_WIDTH_RATIO = 0.001
                ANNOTATION_BACKGROUND_OPACITY = 0.97
                ANNOTATION_MARGIN = 6
                MARKER_COLOR_REFERENCE_AXIS = "#fff0c2"
                MARKER_COLOR_REFERENCE_POINT = "#dfad62"
                MARKER_COLOR_MOMENT = "#f1c40f"
                MARKER_COLOR_SPRING = "#c084fc"
                MARKER_COLOR_BOUNDARY = "#4aa3df"
                MARKER_COLOR_PENALTY = "#ec4899"
                MARKER_COLOR_ANNOTATION_ERROR = "#e74c3c"
                COUPLING_NORMAL_OFFSET_RATIO = 0.0015
                COUPLING_BOUNDARY_WIDTH_RATIO = 0.0015
                COUPLING_SPOKE_WIDTH_RATIO = 0.0011
                COUPLING_LINE_WIDTH_RATIO = 0.0015
                COUPLING_LINE_OPACITY = 0.82
                COUPLING_MARKER_SCALE_RATIO = 0.65
                COUPLING_SPOKE_COUNT = 8
                LOAD_ARROW_LABEL_OFFSET_RATIO = 1.15
                MOMENT_ARC_END_RADIANS = 5.183627878423159
                MOMENT_ARC_SAMPLES = 48
                MOMENT_LABEL_OFFSET_RATIO = 1.35
                SPRING_TURNS = 6
                SPRING_SAMPLES = 64
                SPRING_WAVE_AMPLITUDE_RATIO = 0.015
                SPRING_WAVE_LENGTH_RATIO = 0.04
                SPRING_WIDTH_RATIO = 0.0025
                SPRING_WIDTH_LENGTH_RATIO = 0.01
                SPRING_WAVE_CYCLES = 12.0
                REFERENCE_POINT_THETA_RESOLUTION = 20
                REFERENCE_POINT_PHI_RESOLUTION = 16
                REFERENCE_POINT_SPECULAR = 0.55
                REFERENCE_POINT_AXIS_LENGTH_RATIO = 0.018
                REFERENCE_POINT_AXIS_WIDTH_RATIO = 0.0012
                MARKER_RADIUS_RATIO = 0.008
                REFERENCE_POINT_RADIUS_RATIO = 0.01
                NON_ASCII_CHARACTER_WIDTH_RATIO = 1.65
                CALLOUT_MIN_WIDTH_RATIO = 0.11
                CALLOUT_TEXT_WIDTH_RATIO = 0.0018
                CALLOUT_MAX_WIDTH_RATIO = 0.25
                CALLOUT_GAP_RATIO = 0.035
                CALLOUT_LINE_HEIGHT_PX = 14.0
                CALLOUT_VERTICAL_PADDING_PX = 12.0
                CALLOUT_GAP_PX = 8.0
                MOMENT_RADIUS_RATIO = 0.045
                MOMENT_TUBE_RADIUS_RATIO = 0.0025
                MOMENT_ARROW_LENGTH_RATIO = 0.45
                CALLOUT_MIN_SEPARATION_TOLERANCE = 1e-12
                DIRECTION_ALIGNMENT_THRESHOLD = 0.85

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
                DIALOG_SIZE = (1250, 850)
                TITLE_FONT_SIZE = 22
                LEFT_COLUMN_RIGHT_MARGIN = 12
                SCROLL_MINIMUM_WIDTH = 475
                LAYER_TABLE_MINIMUM_HEIGHT = 155
                LAYER_ADDED_LENGTH = 40.0
                WORKSPACE_CHANNEL_LIST_MAXIMUM_HEIGHT = 115
                PRESSURE_MAX_KPA = 1000.0
                PRESSURE_DECIMALS = 1
                OBJECTIVE_LIST_MINIMUM_HEIGHT = 74
                OBJECTIVE_LIST_MAXIMUM_HEIGHT = 125
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
                PREVIEW_MINIMUM_SIZE = (300, 350)
                PREVIEW_BACKGROUND = "#17212e"
                PREVIEW_TEXT_COLOR = "#b4c5db"
                PREVIEW_HEADING_POSITION = (16, 25)
                PREVIEW_EDGE_COLOR = "#94acc4"
                PREVIEW_AXIS_ORIGIN = (48, 58)
                PREVIEW_AXIS_LENGTH = 30
                PREVIEW_CAPTION_INSET = (85, 42, 95, 36)
                PREVIEW_AXIS_COLORS = ("#f18b85", "#79d795", "#85bafa")
                PREVIEW_AXIS_LABELS = ("X", "Y", "Z")
                PREVIEW_AXIS_LINE_WIDTH = 2
                PREVIEW_EDGE_LINE_WIDTH = 1

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

            class PREVIEW:
                BODY_RESOLUTION = 32
                SPHERE_THETA_RESOLUTION = 20
                SPHERE_PHI_RESOLUTION = 16
                CAVITY_CYLINDER_RESOLUTION = 24
                CAVITY_COLORS = ("#69ddd0", "#f4bb69", "#a6a0ef", "#f596af")
                BODY_COLOR = "#417ba4"
                BODY_TRANSPARENCY_ALPHA = 48
                OPAQUE_ALPHA = 210
                LIGHT_INTENSITY_SCALE = 100
                OUTLINE_CIRCLE_SAMPLES = 49
                MINIMUM_PROJECTED_SPAN = 1.0
                HORIZONTAL_MARGIN = 80
                VERTICAL_MARGIN = 110

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
