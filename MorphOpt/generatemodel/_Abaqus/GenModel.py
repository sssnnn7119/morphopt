# -*- coding: mbcs -*-
#
# Abaqus/CAE Release 2020 replay file
# Internal Version: 2019_09_14-01.49.31 163176
# Run by 24391 on Thu Dec  9 12:31:49 2021

import os
from tokenize import Double

from abaqus import *
from abaqusConstants import *
from caeModules import *
from driverUtils import executeOnCaeStartup

# adjoint moment module


def Find_Surf(surf_tuple, obj):
    pl = []
    for i in range(len(surf_tuple)):
        l1 = obj.getClosest(surf_tuple[i], searchTolerance=1)
        if len(l1) > 0:
            if pl == []:
                pl = obj.findAt((l1[0][1], ))
            else:
                pl += obj.findAt((l1[0][1], ))
    return pl


# Read parameter file: parameters are stored as string
def Read_Para_Base():
    with open("__FEM_Para_Base.txt", 'r') as File_Para:
        file = File_Para.readlines()
    material = []
    for line in file:
        tmp = line.split('*')
        if tmp[0] == 'Surfaces':
            surface_type = [int(x) for x in tmp[1].split()]
        if tmp[0] == 'Material':
            material += [tmp[1].split()]
        if tmp[0] == 'SeedSize':
            seed_size = float(tmp[1])
    return surface_type, material, seed_size

# load model from file
def Import_Part(path, part_name):
    step = mdb.openStep(path, scaleFromFile=OFF)
    mdb.models['Model-1'].PartFromGeometryFile(name=part_name,
                                               geometryFile=step,
                                               combine=False,
                                               mergeSolidRegions=True,
                                               dimensionality=THREE_D,
                                               type=DEFORMABLE_BODY)


def Merge_Surface(p, surfs):
    v = set()
    for surface in surfs:
        v =v.union(set(surface.getVertices()))
    e = set()
    for surface in surfs:
        e =e.union(set(surface.getEdges()))
    e = part.EdgeArray([p.edges[faceIndex] for faceIndex in e])
    v = part.VertexArray([p.vertices[faceIndex] for faceIndex in v])
    pickedEntities = (
        e,
        v,
    )
    p.ignoreEntity(entities=pickedEntities)


# assemble all surfaces into a solid
def Assemble_Surfaces(base_name, void_name_list):
    # import as assembly
    a = mdb.models['Model-1'].rootAssembly
    a.DatumCsysByDefault(CARTESIAN)
    base_part = mdb.models['Model-1'].parts[base_name]
    a.Instance(name=base_name + '-1', part=base_part, dependent=ON)
    void_parts_list = []
    for name in void_name_list:
        void_parts_list.append(mdb.models['Model-1'].parts[name])
        a.Instance(name=name + '-1', part=void_parts_list[-1], dependent=ON)
    # cut the model
    for void_name in void_name_list:
        a = mdb.models['Model-1'].rootAssembly
        a.InstanceFromBooleanCut(
            name=base_name,
            instanceToBeCut=mdb.models['Model-1'].rootAssembly.instances[
                base_name + '-1'],
            cuttingInstances=(a.instances[void_name + '-1'], ),
            originalInstances=DELETE)
        mdb.models['Model-1'].rootAssembly.features.changeKey(
            fromName=base_name+'-2', toName=base_name+'-1')

# find all surface that connect
def Find_Connected_Surfaces(all_surfaces, surface0_index):
    set0 = {surface0_index}
    queue = set()
    adjacentFaces = all_surfaces[surface0_index].getAdjacentFaces()
    queue.update(set([i.index for i in adjacentFaces]))
    while len(queue)>0:
        now = queue.pop()
        set0.add(now)
        adjacentFaces = all_surfaces[now].getAdjacentFaces()
        queue.update(set([i.index for i in adjacentFaces]))
        set.difference_update(queue, set0)
    return set0

###==============import Data===============###

workdir = os.path.split(os.path.realpath('__file__'))[0]
workdir = os.path.abspath(os.path.dirname(os.getcwd()))
workdir = workdir + "\\Cache\\"
# JOB NAME
JOBNAME = 'TopOptRun'

os.chdir(workdir)

surface_type, material, seed_size = Read_Para_Base()

# get the sample points of each surface
surface_info = []
for i in range(len(surface_type)):
    surface_info.append([])
    if surface_type[i] == 0:  # 0:AllSurface, 1:Head, 2:Bottom, 3:Lateral
        f = open(workdir + "__FEM__surface-%d.csv" % i, 'r')
        data = f.readlines()
        f.close()
        surface_info[i].append(
            tuple([
                tuple([tuple(map(float, data[0].split(',')))]),
            ]))
        for j in range(len(data) - 1):
            surface_info[i][0] += (tuple(
                [tuple(map(float, data[j + 1].split(',')))]), )
        surface_info[i].append(
            tuple([
                tuple([tuple(map(float, data[0].split(',')))]),
                tuple([tuple(map(float, data[1].split(',')))])
            ]))
        surface_info[i].append(
            tuple([
                tuple([tuple(map(float, data[2].split(',')))]),
                tuple([tuple(map(float, data[3].split(',')))])
            ]))
        surface_info[i].append(surface_info[i][0][4:])
    if surface_type[i] == 1:  # 0:AllSurface, 1:Head, 2:Bottom
        f = open(workdir + "__FEM__surface-%d.csv" % i, 'r')
        data = f.readlines()
        f.close()
        surface_info[i].append(
            tuple([
                tuple([tuple(map(float, data[0].split(',')))]),
            ]))
        for j in range(len(data) - 1):
            surface_info[i][0] += (tuple(
                [tuple(map(float, data[j + 1].split(',')))]), )

###==============import model==============###
void_name_list = []
Import_Part('__surface-0.stp', 'final_model')
for i in range(len(surface_type) - 1):
    Import_Part('__surface-%d.stp' % (i+1), 'surface_%d' % (i + 1))
    void_name_list.append('surface_%d' % (i + 1))

Assemble_Surfaces('final_model', void_name_list=void_name_list)

###==============find surface==============###
p = mdb.models['Model-1'].parts['final_model']


surface_part = []
for i in range(len(surface_type)):
    f = p.faces
    # define sets
    try:
        if surface_type[i] == 1:
            face0_index = Find_Surf(surface_info[i][0], f)[0].index
            surf_index = Find_Connected_Surfaces(f, face0_index)
            faces_array = part.FaceArray([f[faceIndex] for faceIndex in surf_index])
            # Merge_Surface(p, faces_array)
        f = p.faces
        face0_index = Find_Surf(surface_info[i][0], f)[0].index
        surf_index = Find_Connected_Surfaces(f, face0_index)
        faces_array = part.FaceArray([f[faceIndex] for faceIndex in surf_index])
        p.Set(faces=faces_array, name='surface_%d_All' % i)
        p.Surface(side1Faces=faces_array,
            name='surface_%d_All' % i)
        
    except:
        abc = 1
    if surface_type[i] == 0:
        try:
            p.Set(faces=Find_Surf(surface_info[i][1], f),
                    name='surface_%d_Head' % i)
        except:
            abc = 1
        try:
            p.Set(faces=Find_Surf(surface_info[i][2], f),
                  name='surface_%d_Bottom' % i)
        except:
            abc = 1
        try:
            p.Set(faces=Find_Surf(surface_info[i][3], f),
                  name='surface_%d_Lateral' % i)
        except:
            abc = 1

###==============define set===================###
p = mdb.models['Model-1'].parts['final_model']
c = p.cells
region = p.Set(cells=c, name='RubberSet')
###==============define material==============###

for mat in material:
    if int(mat[2]) == 1:
        ELAST_MAT = (float(mat[3])/2, 2/float(mat[4]), 0.0, 0.0, 0.0, 0.0)
        ELAST_Density = float(mat[1])
        mdb.models['Model-1'].Material(name=mat[0])
        mdb.models['Model-1'].materials[mat[0]].Hyperelastic(
            materialType=ISOTROPIC,
            testData=OFF,
            type=NEO_HOOKE,
            volumetricResponse=VOLUMETRIC_DATA,
            table=(ELAST_MAT, ))
        mdb.models['Model-1'].materials[mat[0]].Density(table=((ELAST_Density, ), ))
        mdb.models['Model-1'].HomogeneousSolidSection(name=mat[0],
                                                    material=mat[0],
                                                    thickness=None)

###==============assign material==============###

p = mdb.models['Model-1'].parts['final_model']
region = p.sets['RubberSet']
p.SectionAssignment(region=region,
                    sectionName=material[0][0],
                    offset=0.0,
                    offsetType=MIDDLE_SURFACE,
                    offsetField='',
                    thicknessAssignment=FROM_SECTION)

###==============Mesh==============###

p = mdb.models['Model-1'].parts['final_model']
p.seedPart(size=seed_size, deviationFactor=0.1, minSizeFactor=0.4)

p = mdb.models['Model-1'].parts['final_model']
c = p.cells

p.setMeshControls(regions=c, elemShape=TET, technique=FREE, sizeGrowthRate=1.2)

# for quadratic element
# elemType1 = mesh.ElemType(elemCode=C3D20R, elemLibrary=STANDARD)
# elemType2 = mesh.ElemType(elemCode=C3D15, elemLibrary=STANDARD)
# elemType3 = mesh.ElemType(elemCode=C3D10, elemLibrary=STANDARD)

# for linear element
elemType1 = mesh.ElemType(elemCode=C3D8R, elemLibrary=STANDARD)
elemType2 = mesh.ElemType(elemCode=C3D6, elemLibrary=STANDARD)
elemType3 = mesh.ElemType(elemCode=C3D4, elemLibrary=STANDARD)

p = mdb.models['Model-1'].parts['final_model']
c = p.cells
pickedRegions = (c, )
p.setElementType(regions=pickedRegions,
                 elemTypes=(elemType1, elemType2, elemType3))

p = mdb.models['Model-1'].parts['final_model']
p.generateMesh()

###==============BC==============###
a = mdb.models['Model-1'].rootAssembly
region = a.instances['final_model-1'].sets['surface_0_Bottom']
mdb.models['Model-1'].DisplacementBC(name='BC-1',
                                     createStepName='Initial',
                                     region=region,
                                     u1=SET,
                                     u2=SET,
                                     u3=SET,
                                     ur1=SET,
                                     ur2=SET,
                                     ur3=SET,
                                     amplitude=UNSET,
                                     distributionType=UNIFORM,
                                     fieldName='',
                                     localCsys=None)

###================Job==================###
if os.path.exists('ADJ_Body_Force.for'):
    USUB = workdir + "ADJ_Body_Force.for"
else:
    USUB = ""
mdb.Job(name=JOBNAME,
        model='Model-1',
        description='',
        type=ANALYSIS,
        atTime=None,
        waitMinutes=0,
        waitHours=0,
        queue=None,
        memory=90,
        memoryUnits=PERCENTAGE,
        getMemoryFromAnalysis=True,
        explicitPrecision=SINGLE,
        nodalOutputPrecision=FULL,
        echoPrint=OFF,
        modelPrint=OFF,
        contactPrint=OFF,
        historyPrint=OFF,
        userSubroutine=USUB,
        scratch='',
        resultsFormat=ODB,
        multiprocessingMode=THREADS,
        numCpus=8,
        numDomains=8,
        numGPUs=1)

mdb.jobs['TopOptRun'].writeInput(consistencyChecking=OFF)
mdb.jobs['TopOptRun'].waitForCompletion()

###==============save model==================###
mdb.saveAs(pathName=workdir + "TopAbqLS")
