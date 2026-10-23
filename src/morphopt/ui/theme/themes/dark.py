"""Built-in dark theme."""

from dataclasses import replace

from ..palette import (
    ChartStyle,
    CodeEditorPalette,
    DEFAULT_LAYOUT_STYLE,
    DEFAULT_VIEWER_STYLE,
    QuickstartPreviewStyle,
    ThemePalette,
)


_viewer = replace(
    DEFAULT_VIEWER_STYLE,
    render=replace(
        DEFAULT_VIEWER_STYLE.render,
        background="#0e131c",
        legend_background="#1a202a",
        legend_text_color=(0.86, 0.9, 0.95),
        coupling_surface_color="#dcae67",
        coupling_edge_color="#edc27e",
        coupling_spoke_color="#dfad62",
        coupling_label_color="#edc27e",
        annotation_text_color="#dce4ee",
        annotation_background_color="#202833",
    ),
)

DARK = ThemePalette(
    window="#121417",
    panel="#191d24",
    input="#232832",
    border="#333b48",
    text="#e7ebf0",
    muted_text="#9ba6b5",
    heading_text="#dce5f0",
    accent="#1769aa",
    accent_hover="#2080cc",
    selection="#285b80",
    selection_text="#ffffff",
    button="#29384b",
    button_hover="#354b64",
    button_pressed="#202d3d",
    disabled="#282d35",
    disabled_text="#717d8a",
    danger="#843b40",
    danger_hover="#a4484d",
    on_accent="#ffffff",
    warning="#e4b44f",
    error="#f07178",
    tree_error_background="#3b272c",
    tree_error_text="#ffb4ba",
    section_heading_size=14,
    dialog_title_size=22,
    code_editor=CodeEditorPalette(
        font_family="DejaVu Sans Mono",
        font_size=10,
        keyword="#c678dd",
        self_name="#e5c07b",
        number="#d19a66",
        string="#98c379",
        comment="#7f8997",
        decorator="#e06c75",
    ),
    chart=ChartStyle(
        background="#121212",
        text="#dce4ee",
        grid="#8793a3",
        line="#38c7ce",
    ),
    viewer=_viewer,
    quickstart_preview=QuickstartPreviewStyle(
        background="#17212e",
        text="#b4c5db",
        heading="#b4c5db",
        edge="#94acc4",
        axis_colors=("#f18b85", "#79d795", "#85bafa"),
        body="#417ba4",
        cavities=("#69ddd0", "#f4bb69", "#a6a0ef", "#f596af"),
    ),
    deformation_mesh_color="#2878b5",
    history_branch_colors=(
        "#48a9e8", "#d08bda", "#e3a44b", "#63bd91", "#dd7373", "#8e9ee8",
    ),
    layout=DEFAULT_LAYOUT_STYLE,
)
