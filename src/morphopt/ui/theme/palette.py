"""Typed, immutable visual settings shared by every UI renderer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeEditorPalette:
    font_family: str
    font_size: int
    keyword: str
    self_name: str
    number: str
    string: str
    comment: str
    decorator: str


@dataclass(frozen=True)
class ChartStyle:
    background: str
    text: str
    grid: str
    line: str
    line_width: float = 1.5
    marker_size: float = 5.0
    grid_width: float = 0.5


@dataclass(frozen=True)
class QuickstartPreviewStyle:
    background: str
    text: str
    heading: str
    edge: str
    axis_colors: tuple[str, str, str]
    body: str
    cavities: tuple[str, ...]
    body_transparency_alpha: int = 48
    opaque_alpha: int = 210
    light_intensity: int = 100
    light_direction: tuple[float, float, float] = (1.0, -1.0, 2.0)
    light_ambient: float = 0.65
    light_contrast: float = 0.35
    surface_normal_tolerance: float = 1e-12
    minimum_size: tuple[int, int] = (300, 350)
    heading_position: tuple[int, int] = (16, 25)
    edge_width: float = 1.0
    axis_origin: tuple[int, int] = (48, 58)
    axis_length: int = 30
    axis_labels: tuple[str, str, str] = ("X", "Y", "Z")
    axis_width: float = 2.0
    caption_inset: tuple[int, int, int, int] = (85, 42, 95, 36)
    body_resolution: int = 32
    cavity_cylinder_resolution: int = 24
    sphere_theta_resolution: int = 20
    sphere_phi_resolution: int = 16
    horizontal_margin: int = 80
    vertical_margin: int = 110
    minimum_projected_span: float = 1.0
    outline_circle_samples: int = 49


@dataclass(frozen=True)
class WorkbenchLayout:
    output_name_width: int = 180
    path_minimum_width: int = 120
    directory_button_width: int = 30
    device_selector_width: int = 150
    left_minimum_width: int = 230
    editor_minimum_width: int = 440
    left_split_sizes: tuple[int, int] = (500, 260)
    main_split_sizes: tuple[int, int, int] = (230, 560, 460)
    description_margins: tuple[int, int, int, int] = (16, 16, 16, 16)


@dataclass(frozen=True)
class HistoryLayout:
    row_height: int = 28
    graph_left_margin: int = 12
    graph_right_margin: int = 14
    graph_text_gap: int = 6
    graph_lane_spacing: int = 18
    graph_line_width: int = 2
    graph_node_radius: int = 4
    graph_current_node_radius: int = 5


@dataclass(frozen=True)
class ObserverLayout:
    step_button_width: int = 30
    iteration_label_minimum_width: int = 70
    option_panel_width: int = 160
    option_split_sizes: tuple[int, int] = (160, 1100)
    content_stretch_factors: tuple[int, int] = (5, 1)
    content_split_sizes: tuple[int, int] = (700, 180)


@dataclass(frozen=True)
class UpdaterEditorLayout:
    selection_scroll_margins: tuple[int, int] = (10, 10)
    item_button_height: int = 30
    distance_matrix_button_minimum_width: int = 110
    distance_matrix_panel_margins: tuple[int, int, int, int] = (8, 8, 8, 8)
    distance_matrix_panel_spacing: int = 6
    distance_matrix_table_maximum_height: int = 440
    distance_matrix_table_base_height: int = 40
    distance_matrix_table_row_height: int = 30
    distance_matrix_table_section_height: int = 26


@dataclass(frozen=True)
class WidgetLayout:
    action_button_height: int = 30
    item_action_button_width: int = 32
    objective_selector_height: int = 30
    multiline_field_minimum_height: int = 120
    path_button_width: int = 28
    continue_dialog_minimum_width: int = 380
    form_contents_margins: tuple[int, int, int, int] = (8, 4, 8, 4)
    collection_contents_margins: tuple[int, int, int, int] = (4, 4, 4, 4)
    collection_spacing: int = 8
    standard_form_spacing: int = 6
    action_row_vertical_margin: int = 2
    action_grid_columns: int = 2
    action_grid_spacing: int = 6
    code_completion_minimum_width: int = 260
    code_editor_minimum_height: int = 140
    code_editor_toolbar_spacing: int = 2
    custom_class_base_minimum_width: int = 400
    model_summary_indentation: int = 18
    model_summary_name_column_width: int = 240


@dataclass(frozen=True)
class QuickstartLayout:
    dialog_size: tuple[int, int] = (1250, 850)
    left_column_right_margin: int = 12
    scroll_minimum_width: int = 475
    layer_table_minimum_height: int = 155
    workspace_channel_list_maximum_height: int = 115
    objective_list_minimum_height: int = 74
    objective_list_maximum_height: int = 125


@dataclass(frozen=True)
class FiniteElementLayout:
    split_sizes: tuple[int, int] = (650, 850)
    iteration_selector_minimum_width: int = 100
    load_table_minimum_height: int = 210
    output_maximum_blocks: int = 1500


@dataclass(frozen=True)
class LayoutStyle:
    """Shared widget geometry, spacing, and initial window proportions."""

    main_window_size: tuple[int, int] = (1500, 880)
    zero_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    zero_spacing: int = 0
    toolbar_icon_size: tuple[int, int] = (20, 20)
    language_selector_width: int = 110
    theme_selector_width: int = 100
    helper_code_minimum_height: int = 220
    workbench: WorkbenchLayout = WorkbenchLayout()
    history: HistoryLayout = HistoryLayout()
    observer: ObserverLayout = ObserverLayout()
    updater_editor: UpdaterEditorLayout = UpdaterEditorLayout()
    widgets: WidgetLayout = WidgetLayout()
    quickstart: QuickstartLayout = QuickstartLayout()
    finite_element: FiniteElementLayout = FiniteElementLayout()


DEFAULT_LAYOUT_STYLE = LayoutStyle()


@dataclass(frozen=True)
class ViewerGeometryStyle:
    instance_colors: tuple[str, ...]
    uninstanced_color: str
    cylinder_resolution: int = 64
    sphere_theta_resolution: int = 48
    sphere_phi_resolution: int = 48
    boundary_relative_tolerance: float = 1e-6
    boundary_absolute_tolerance: float = 1e-8
    rotation_zero_tolerance: float = 1e-12
    extra_instance_hue_step: float = 0.61803398875
    extra_instance_hue_offset: float = 0.11
    extra_instance_saturation: float = 0.4
    extra_instance_value: float = 0.76
    cad_face_ambient: float = 0.2
    cad_face_diffuse: float = 0.72
    cad_face_specular: float = 0.22
    cad_face_specular_power: int = 28
    cad_edge_color: str = "#f5f6f8"
    cad_edge_width: float = 2.5
    cad_label_font_size: int = 14
    cad_label_shape_color: str = "#101722"
    cad_label_shape_opacity: float = 0.94
    material_region_color: str = "#7f8c8d"
    material_region_fill_opacity: float = 0.03
    material_region_opacity: float = 0.6
    boundary_shell_opacity: float = 0.28
    picked_face_color: str = "#ffb347"
    pick_drag_distance: int = 5


@dataclass(frozen=True)
class ViewerLoadsStyle:
    pressure_surface_color: str = "#38c7ce"
    pressure_arrow_color: str = "#a8f5da"
    pressure_opacity: float = 0.9
    pressure_ambient: float = 0.4
    pressure_diffuse: float = 0.6
    pressure_specular: float = 0.15
    pressure_preview_offset_ratio: float = 0.0015
    pressure_zero_tolerance: float = 1e-12
    pressure_surface_samples: int = 3
    force_color: str = "#e74c3c"
    body_force_color: str = "#ff8c42"
    penalty_color: str = "#ec4899"
    boundary_color: str = "#398bd0"
    boundary_outline_color: str = "#8bc8ff"
    boundary_marker_color: str = "#4aa3df"
    boundary_opacity: float = 0.6
    boundary_preview_offset_ratio: float = 0.0015
    boundary_outline_width_ratio: float = 0.0018
    load_arrow_length_ratio: float = 0.04
    load_arrow_tip_length_ratio: float = 0.25
    load_arrow_tip_radius_ratio: float = 0.055
    load_arrow_shaft_radius_ratio: float = 0.015
    coupling_spoke_count: int = 8
    glyph_zero_tolerance: float = 1e-12


@dataclass(frozen=True)
class ViewerRenderStyle:
    background: str
    result_colormap: str = 'viridis'
    minimum_scalar_span: float = 1e-12
    orientation_axes_viewport: tuple[float, float, float, float] = (0.0, 0.0, 0.18, 0.18)
    orientation_axis_colors: tuple[str, str, str] = ('#df624f', '#53a76a', '#518bd4')
    depth_peels: int = 8
    depth_peeling_occlusion_ratio: float = 0.0
    mesh_ambient: float = 0.17
    mesh_diffuse: float = 0.78
    mesh_specular: float = 0.24
    mesh_specular_power: int = 30
    legend_min_width: float = 0.13
    legend_max_width: float = 0.28
    legend_base_width: float = 0.055
    legend_name_width_ratio: float = 0.008
    legend_max_height: float = 0.4
    legend_row_height: float = 0.025
    legend_padding: int = 4
    legend_background: str = "#1a202a"
    legend_background_opacity: float = 0.8
    legend_text_color: tuple[float, float, float] = (0.86, 0.9, 0.95)
    legend_font_family: str = "arial"
    legend_font_size: int = 10
    label_font_size: int = 10
    label_margin: int = 6
    label_opacity: float = 0.97
    coupling_surface_opacity: float = 0.46
    coupling_surface_color: str = "#dcae67"
    coupling_edge_color: str = "#edc27e"
    coupling_spoke_color: str = "#dfad62"
    coupling_label_color: str = "#edc27e"
    coupling_label_side: float = 1.0
    reference_point_label_side: float = -1.0
    annotation_text_color: str = "#dce4ee"
    annotation_background_color: str = "#202833"
    annotation_leader_opacity: float = 0.68
    annotation_leader_width_ratio: float = 0.001
    annotation_background_opacity: float = 0.97
    annotation_margin: int = 6
    marker_color_reference_axis: str = "#fff0c2"
    marker_color_reference_point: str = "#dfad62"
    marker_color_moment: str = "#f1c40f"
    marker_color_spring: str = "#c084fc"
    marker_color_boundary: str = "#4aa3df"
    marker_color_penalty: str = "#ec4899"
    marker_color_annotation_error: str = "#e74c3c"
    coupling_normal_offset_ratio: float = 0.0015
    coupling_boundary_width_ratio: float = 0.0015
    coupling_spoke_width_ratio: float = 0.0011
    coupling_line_width_ratio: float = 0.0015
    coupling_line_opacity: float = 0.82
    coupling_marker_scale_ratio: float = 0.65
    coupling_spoke_count: int = 8
    load_arrow_label_offset_ratio: float = 1.15
    moment_arc_end_radians: float = 5.183627878423159
    moment_arc_samples: int = 48
    moment_label_offset_ratio: float = 1.35
    spring_turns: int = 6
    spring_samples: int = 64
    spring_wave_amplitude_ratio: float = 0.015
    spring_wave_length_ratio: float = 0.04
    spring_width_ratio: float = 0.0025
    spring_width_length_ratio: float = 0.01
    spring_wave_cycles: float = 12.0
    reference_point_theta_resolution: int = 20
    reference_point_phi_resolution: int = 16
    reference_point_specular: float = 0.55
    reference_point_axis_length_ratio: float = 0.018
    reference_point_axis_width_ratio: float = 0.0012
    marker_radius_ratio: float = 0.008
    reference_point_radius_ratio: float = 0.01
    non_ascii_character_width_ratio: float = 1.65
    callout_min_width_ratio: float = 0.11
    callout_text_width_ratio: float = 0.0018
    callout_max_width_ratio: float = 0.25
    callout_gap_ratio: float = 0.035
    callout_line_height_px: float = 14.0
    callout_vertical_padding_px: float = 12.0
    callout_gap_px: float = 8.0
    moment_radius_ratio: float = 0.045
    moment_tube_radius_ratio: float = 0.0025
    moment_arrow_length_ratio: float = 0.45
    callout_min_separation_tolerance: float = 1e-12
    direction_alignment_threshold: float = 0.85


@dataclass(frozen=True)
class ViewerStyle:
    geometry: ViewerGeometryStyle
    loads: ViewerLoadsStyle
    render: ViewerRenderStyle
    scene_fallback_diagonal: float = 10.0
    glyph_width_ratio: float = 4.0


DEFAULT_VIEWER_STYLE = ViewerStyle(
    geometry=ViewerGeometryStyle(
        instance_colors=("#71899a", "#a77b6d", "#6f8e83", "#887e9d", "#aa905f", "#82916a", "#a47787", "#718397"),
        uninstanced_color="#77838c",
    ),
    loads=ViewerLoadsStyle(),
    render=ViewerRenderStyle(background="#0e131c"),
)


@dataclass(frozen=True)
class ThemePalette:
    """Complete immutable appearance configuration for one UI theme."""

    window: str
    panel: str
    input: str
    border: str
    text: str
    muted_text: str
    heading_text: str
    accent: str
    accent_hover: str
    selection: str
    selection_text: str
    button: str
    button_hover: str
    button_pressed: str
    disabled: str
    disabled_text: str
    danger: str
    danger_hover: str
    on_accent: str
    warning: str
    error: str
    tree_error_background: str
    tree_error_text: str
    section_heading_size: int
    dialog_title_size: int
    code_editor: CodeEditorPalette
    chart: ChartStyle
    viewer: ViewerStyle
    quickstart_preview: QuickstartPreviewStyle
    deformation_mesh_color: str
    history_branch_colors: tuple[str, ...]
    layout: LayoutStyle

    @property
    def viewer_background(self) -> str:
        """Compatibility shortcut for code that needs only the viewport clear color."""
        return self.viewer.render.background
