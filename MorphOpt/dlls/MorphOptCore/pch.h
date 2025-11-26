// pch.h: 这是预编译标头文件。
// 下方列出的文件仅编译一次，提高了将来生成的生成性能。
// 这还将影响 IntelliSense 性能，包括代码完成和许多代码浏览功能。
// 但是，如果此处列出的文件中的任何一个在生成之间有更新，它们全部都将被重新编译。
// 请勿在此处添加要频繁更新的文件，这将使得性能优势无效。

#ifndef PCH_H
#define PCH_H

// 添加要在此处预编译的标头
#include "framework.h"

#endif //PCH_H

#ifdef IMPORT_DLL
#else
#define IMPORT_DLL extern "C" __declspec(dllimport) //指的是允许将其给外部调用
#endif


// DLL接口声明

/**
 * @brief 计算符合条件的点对
 * @param numPoints 点的数量
 * @param points 点坐标数组，格式为[x1,y1,z1,x2,y2,z2,...]
 * @param normals 法向量数组，格式为[nx1,ny1,nz1,nx2,ny2,nz2,...]
 * @param distanceThreshold 距离阈值
 * @return 符合条件的点对数量
 */
IMPORT_DLL int CalculatePointPairs(int numPoints, double* points, double* normals, int* surf_ind, double distanceThreshold);

/**
 * @brief 读取计算好的点对数据
 * @param pairData 用于存储点对数据的整型数组，格式为[idx1_1,idx2_1,dist_1,idx1_2,idx2_2,dist_2,...]
 * @return 是否成功读取点对数据
 */
IMPORT_DLL bool GetPointPairs(int* pairData);