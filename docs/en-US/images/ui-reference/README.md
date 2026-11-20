# Reference images for modules and interfaces

[简体中文](../../../zh-CN/images/ui-reference/README.md)

This directory service includes [UI module reference](../../ui-reference.md). The module images and the quick start section share the same images; no duplicate images are created. All interface images are collected from the same source. See [Screenshot Index](../gallery.md) and [Collection list](../current-capture-manifest.json) for more details.

<a id="section-来源与边界"></a>

## 1 Sources and Boundaries

- Define the use of the repository example for image processing, the quick start template, and the interface demonstration model. The result pages use the bending actuator and SIMP's CPU for archiving purposes.
- Descriptions of interface parameters or geometric previews for the Box, CAD, CPGEO, spring, contact, SIMP, and custom classes should not be used to assume convergence has been achieved.
- The STEP/STL/INP document sample is located at [Asset description](../import-samples.md). After the files are imported, the material distribution, loads, and boundaries need to be verified again.
- The image of the dialog box is taken from an actual Qt window. The export operation was cancelled after the screenshot was taken, so no user files were created.

<a id="section-字体与原始像素"></a>

## 2 Fonts and original pixels

The newly collected images use the system Western font and size through the application’s font manager. The installed Simplified Chinese font is also clearly selected. The actual Chinese characters in the collected images all come from Noto Sans CJK SC. The 3D annotations use the same SC font set. The preference is to write to the temporary directory, and the user’s desktop settings remain unchanged. The sources of each font character and its actual shape can be found in [Collection list](../current-capture-manifest.json).

The image retains its original pixels and supports zooming for viewing. It does not use image editing tools to replace the content. For the method of re-collection and the operating environment, please refer to [Illustration instructions for maintenance purposes](../README.md).

<a id="section-命名和接口清单"></a>

## 3 Naming and interface list

The image contains `module/subject.png` elements, such as `loads/penalty-node-direction.png`, `objectives/workspace-objective.png`, and `appearance/font-settings.png`.

[interface-catalog.json](interface-catalog.json) is generated from the current UI registry. It includes components, surfaces, 14 types of CAD operations, 15 categories of loads and connections, materials, update targets, constraints and strategies, as well as 8 types of constitutive parameter definitions. The static fields record the names of components, item types, default values, options, and help. Fields that vary depending on the object type are described in the main text. For example, the instance PenaltyDoF derives from the s-derived nodes and directions. Loads are also recorded in `value_fields`, and are shared with load cases and independent finite element editing.

<a id="section-说明图"></a>

## 4 Illustration diagram

`diagrams/object-references.svg`, `optimization-cycle.svg`, `simp-pipeline.svg`, and `geometric-constraints.svg` respectively refer to object reference, optimization loop, material mapping, and geometric constraint. These diagrams do not represent finite element results; the implementation details are subject to the current module references and source code.
