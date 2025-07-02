#include <iostream>
#include <vector>

#include "pch.h"
#include <cmath>

#include <algorithm>
#include <unordered_map>

#include <omp.h>
// 三维点结构
struct Point3D {
    double x, y, z;

    Point3D() : x(0), y(0), z(0) {}
    Point3D(double _x, double _y, double _z) : x(_x), y(_y), z(_z) {}

    // 计算两点之间的欧氏距离
    double distance(const Point3D& other) const {
        double dx = x - other.x;
        double dy = y - other.y;
        double dz = z - other.z;
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    }

    // 向量点乘
    double dot(const Point3D& other) const {
        return x * other.x + y * other.y + z * other.z;
    }

    // 向量归一化
    Point3D normalize() const {
        double len = std::sqrt(x * x + y * y + z * z);
        if (len < 1e-8) return *this;
        return Point3D(x / len, y / len, z / len);
    }
};

// 点对结构，存储符合条件的点对
struct PointPair {
    int idx1, idx2;
    double distance;

    PointPair(int i1, int i2, double dist) : idx1(i1), idx2(i2), distance(dist) {}
};

// 表面点结构：包含位置和法向量
struct SurfacePoint {
    Point3D position;
    Point3D normal;
	int surfaceIndex; // 表面索引，可能用于后续处理

    SurfacePoint(const Point3D& pos, const Point3D& norm, const int _surfaceIndex)
        : position(pos), normal(norm.normalize()), surfaceIndex(_surfaceIndex) {
    } // 存储时归一化法向量
};

// 暴力搜索算法 - 用于对比性能和准确度
std::vector<PointPair> bruteForceFindPointPairs(const std::vector<SurfacePoint>& points, double distanceThreshold) {
    std::vector<PointPair> result;
    if (points.size() < 2) return result;

    // 使用OpenMP并行处理
    std::vector<std::vector<PointPair>> threadResults(omp_get_max_threads());

#pragma omp parallel for schedule(dynamic)
    for (int i = 0; i < points.size(); ++i) {
        const auto& p1 = points[i];
        int threadId = omp_get_thread_num();

        for (int j = i + 1; j < points.size(); ++j) {  // 从i+1开始避免重复检查
            const auto& p2 = points[j];

            // 计算距离
            double dist = p1.position.distance(p2.position);

            // 检查距离是否小于阈值
            if (dist < distanceThreshold) {
                // 检查法向量点乘是否小于0（表示法向量大致相反）
				if (p1.surfaceIndex != p2.surfaceIndex) { // 不同表面直接添加
					threadResults[threadId].emplace_back(i, j, dist);
				}
                else {
                    double dotProduct = p1.normal.dot(p2.normal);
                    if (dotProduct < -0.5) {
                        threadResults[threadId].emplace_back(i, j, dist);
                    }
                }
            }
        }
    }

    // 合并各线程的结果
    for (const auto& threadResult : threadResults) {
        result.insert(result.end(), threadResult.begin(), threadResult.end());
    }

    return result;
}

// 存储计算结果的全局变量

    std::vector<PointPair> g_pointPairs;


// DLL接口：计算点对
int CalculatePointPairs(int numPoints, double* points, double* normals, int* surf_ind, double distanceThreshold) {
    // 清空之前的结果
    g_pointPairs.clear();

    // 参数验证
    if (numPoints <= 0 || points == nullptr || normals == nullptr || distanceThreshold <= 0) {
        return 0;
    }

    // 构建表面点集合
    std::vector<SurfacePoint> surfacePoints;
    surfacePoints.reserve(numPoints);

    for (int i = 0; i < numPoints; ++i) {
        int pIdx = i * 3; // 每个点有3个坐标分量
        Point3D pos(points[pIdx], points[pIdx + 1], points[pIdx + 2]);
        Point3D norm(normals[pIdx], normals[pIdx + 1], normals[pIdx + 2]);
        surfacePoints.emplace_back(pos, norm, surf_ind[i]);
    }

    // 计算点对
    g_pointPairs = bruteForceFindPointPairs(surfacePoints, distanceThreshold);

    // 返回点对数量
    return static_cast<int>(g_pointPairs.size());
}

// DLL接口：读取点对
bool GetPointPairs(int* pairData) {
    if (pairData == nullptr || g_pointPairs.empty()) {
        return false;
    }

    // 每个点对存储两个点的索引
    for (int i = 0; i < g_pointPairs.size(); ++i) {
        const auto& pair = g_pointPairs[i];
        int baseIdx = i * 2; // 每个点对占用2个整数: idx1, idx2
        pairData[baseIdx] = pair.idx1;
        pairData[baseIdx + 1] = pair.idx2;
    }

    return true;
}