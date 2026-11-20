# UI screenshots

[简体中文](../../zh-CN/images/README.md)

From the repository root, use the Python environment in which MorphOpt and its UI dependencies are installed.

```bash
python scripts/docs/capture_ui.py
```

On Linux the default command uses a private virtual display and captures the Chinese and English interfaces in sequence. It requires either Xvfb with `xvfb-run` and `xauth`, or KWin with Xwayland and `dbus-run-session`. Each capture uses temporary application settings. Browse the [English gallery](gallery.md) or [Chinese gallery](../../zh-CN/images/gallery.md).

The script opens real Qt windows, edits model definitions, selects result views and captures the widgets at their original pixel sizes. It covers geometry, load cases, materials, solver and updater settings, custom classes, assets, appearance, camera controls, optimization history, export and finite-element postprocessing.

```bash
python scripts/docs/capture_ui.py --language en-US
python scripts/docs/capture_ui.py --language zh-CN --result /path/to/bending-run
```

Use `--visible` to inspect the capture on the current desktop or run it in a Windows graphical session. Closing the main capture window cancels the batch.

<a id="section-result-data"></a>

## 1 Result data

- The [bending-actuator definition](../../../examples/bending_actuator/bending_actuator.morph) runs for two CPU iterations in a temporary directory. Both languages use this archive for design history, the control net, deformation and GIF previews.
- The finite-element view loads a copy of an archived model, changes `pressure_1` in `load_case_1` from 0.06 MPa to 0.04 MPa and solves again.
- The SIMP example uses the topology quick start with a mesh size of 4. Its first checkpoint supplies the live status, density field and export views.
- The [asset samples](import-samples.md) exercise STEP, STL and INP import.

Pass `--result /path/to/bending-run` to reuse a bending-actuator archive with at least two saved iterations. The SIMP run and the finite-element reanalysis are performed separately.

<a id="section-files-and-verification"></a>

## 2 Files and verification

Each edition uses `images/ui-quickstart/` for workflow illustrations and `images/ui-reference/` for module and field illustrations. Both guides can use the same image. [UI quick start](../ui-quickstart.md) · [UI module reference](../ui-reference.md)

The script stages the images, checks the PNG references in the guides and compares filenames across languages before updating the documentation. The [manifest](current-capture-manifest.json) records source, size, device pixel ratio and font settings. The [interface catalog](ui-reference/interface-catalog.json) comes from the UI registry.
