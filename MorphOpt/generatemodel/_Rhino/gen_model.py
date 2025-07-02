import os
import shutil
import time
import Rhino
import scriptcontext
import rhinoscriptsyntax as rs
import random

def QuadRemesh(obj):
    
    go = Rhino.Input.Custom.GetObject()
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Mesh
    go.SetCommandPrompt("Select Mesh to QuadRemesh")
    rs.SelectObject(obj)
    go.Get()
    if(go.CommandResult() != Rhino.Commands.Result.Success):
        return go.CommandResult()

    mesh = go.Object(0).Mesh()

    qr_params = Rhino.Geometry.QuadRemeshParameters()
    qr_params.AdaptiveQuadCount=True
    qr_params.TargetQuadCount = 3000 + random.randint(-100,100)

    qr_params.AdaptiveSize = 50
    qr_params.DetectHardEdges=False
    
    remeshed = mesh.QuadRemesh(qr_params)
    
    
    scriptcontext.doc.ActiveDoc.Objects.Add(remeshed)
    scriptcontext.doc.ActiveDoc.Views.Redraw
    
    rs.DeleteObject(obj)

    return Rhino.Commands.Result.Success

def Import_Data(import_path, surf_type):
    layers = rs.LayerNames()
    rs.UnselectAllObjects()
    a = rs.ObjectsByLayer(layers[0], True)
    rs.DeleteObjects(a)

    if surf_type == 0:
        f = open(import_path, 'r')
        file = f.readlines()
        f.close()
        
        degreeData = file[0].split(',')
        degree = list(map(int, degreeData[0:2]))

        index = 1

        points = []
        heads = []
        bottoms = []

        uv = list(map(int, file[index].split(',')))
        index += 1
        for j in range(uv[0]*uv[1]):
            points.append(list(map(float, file[index].split(','))))
            if j % uv[1] == 0:
                bottoms.append(list(map(float, file[index].split(','))))
            if j % uv[1] == uv[1]-1:
                heads.append(list(map(float, file[index].split(','))))
            index += 1

        a = rs.AddSrfControlPtGrid(uv, points, degree)


    if surf_type == 1:
        rs.Command("_-Import"+' ' + import_path + ' '+'enter'+' '+'enter')
        layers = rs.LayerNames()
        rs.UnselectAllObjects()
        a = rs.ObjectsByLayer(layers[0], True)[0]
    return a
    
def Surface_Process(a, surf_type):

    
    if surf_type == 0:
        
        rs.UnselectAllObjects()
        rs.SelectObject(a)
        rs.Command("_MakePeriodic Smooth=No enter")

        rs.CapPlanarHoles(a)

    if surf_type == 1:
        rs.MeshToNurb(a, delete_input=True)
#        QuadRemesh(a)
#        rs.DeleteObject(a)
#        
#        layers = rs.LayerNames()
#        rs.UnselectAllObjects()
#        a = rs.ObjectsByLayer(layers[0], True)[0]
#        
#        rs.SelectObject(a)
#        rs.Command('_ToSubD' + ' ' + 'MeshCreases=Yes' + ' ' + 'MeshCreases=Yes' + ' ' + 'enter')
#        rs.DeleteObject(a)
    layers = rs.LayerNames()
    rs.UnselectAllObjects()
    a = rs.ObjectsByLayer(layers[0], True)[0]
    return a

def Export_Data(a, path):
    rs.SelectObject(a)
    rs.Command("_-Export"+' ' + path + ' '+'enter'+' '+'enter')
    rs.Command("Delete enter")

def Task():


    workdir = os.path.dirname(os.path.abspath(__file__))
    
    f = open(workdir + "\\check.txt", 'w')
    f.write('0')
    f.close()
    
    while True:
        time.sleep(0.1)

        try:
            f = open(workdir + "\\check.txt", 'r')
            check = f.readline()
            f.close()
            if check == '-1':
                break
        except:
            continue


        Queue = os.listdir(workdir + "\\TaskQueue")

        # information data:
        # 1. procession type (1:nurbs, 2:stl)
        # 2. filepath of the surface's information
        # 3. path to output


        if len(Queue)>0:
            f = open(workdir + "\\TaskQueue\\" + Queue[0], 'r')
            surf_type = int(f.readline().split()[0])
            path_data = f.readline().split()[0]
            path_output = f.readline().split()[0]
            f.close()

            a = Import_Data(path_data, surf_type)
            a = Surface_Process(a, surf_type)
            Export_Data(a, path_output)

            os.remove(workdir + "\\TaskQueue\\" + Queue[0])

    
if __name__ == '__main__':
    Task()