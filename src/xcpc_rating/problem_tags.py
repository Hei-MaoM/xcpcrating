"""Canonical names for the second, fine-grained problem-tag field.

The seven public axes answer *which broad skill family* a problem belongs to.
``detailTags`` answers *which concrete technique* is used.  This module keeps
one display name per technique and accepts a small compatibility alias table so
old hand-entered records cannot introduce duplicate names.
"""

from __future__ import annotations

from collections.abc import Iterable


DETAIL_TAG_LABELS = (
    "模拟", "构造", "贪心", "排序", "二分查找", "双指针", "前缀和", "差分",
    "枚举", "分治", "倍增", "递归", "交互", "位运算", "随机化", "离散化", "DFS/BFS",
    "最短路", "最小生成树", "拓扑排序", "强连通分量", "割点与桥", "二分图", "网络流", "最大流",
    "匹配", "树形DP", "树上差分", "最近公共祖先", "换根DP", "树链剖分", "欧拉回路",
    "虚树", "点分治", "笛卡尔树", "并查集", "线段树", "树状数组", "堆", "队列", "单调栈", "单调队列", "哈希表",
    "字典树", "平衡树", "字符串哈希", "KMP", "AC自动机", "后缀数组", "后缀自动机", "回文算法",
    "莫队", "分块", "线性基", "李超树", "数论", "素数筛", "最大公约数", "组合数学",
    "容斥", "生成函数", "多项式与NTT", "矩阵快速幂", "矩阵树定理", "线性代数", "概率与期望", "博弈论",
    "计数", "质因数分解", "模运算", "莫比乌斯反演", "背包DP", "区间DP", "状压DP",
    "数位DP", "概率DP", "计数DP", "线性DP", "插头DP", "最长递增子序列", "记忆化搜索", "扫描线",
    "四边形不等式优化", "凸包", "旋转卡壳", "半平面交", "叉积与方向", "立体几何",
    # Additional evidence-backed techniques that occur in official regional
    # tutorials.  They are kept as distinct canonical names so reviewers can
    # preserve a precise technique instead of collapsing it into an empty or
    # generic tag.
    "字符串", "动态规划", "树", "数学", "图论", "几何", "树上路径", "卷积", "整除", "整除分块",
    "根号分治", "二维数点", "点包含判定", "分段", "进位处理", "有向无环图", "最长路", "离线算法",
    "高精度", "对数比较", "圆方树", "分层图", "建图", "集合", "Z函数", "曼哈顿距离", "动态DP",
    "动态树", "矩阵乘法", "多重集合", "LCP", "鸽巢原理", "优化", "区间交", "2-SAT", "快速幂",
    "动态维护", "区间", "判别式", "连通性", "单调性", "网格图", "极角排序", "判环", "递推", "迭代", "子序列",
    "二分图匹配",
    "计算几何", "凸函数", "三分", "最小费用最大流", "对偶图", "回文自动机", "最长公共子串",
    "高维前缀和", "启发式合并", "子集枚举", "暴力", "格雷码", "生成树计数", "素数", "负环",
    "绝对值不等式", "一次函数", "Floyd", "数据结构", "矩阵求逆", "高斯消元", "拉格朗日插值",
    "排列", "珂朵莉树", "线性规划", "树高", "康威生命游戏", "周期性引理", "栈",
    "扩展欧几里得", "类欧几里得", "格林公式", "树的直径", "环形数组", "Fail树", "纳什均衡", "逆序对",
    "子集卷积", "FWT", "周期性", "分类讨论", "线段树合并", "支配树", "折半搜索",
)

DETAIL_TAG_ALIASES = {
    "二分": "二分查找",
    "二分答案": "二分查找",
    "线段树维护": "线段树",
    "树上DP": "树形DP",
    "树形动态规划": "树形DP",
    "后缀自动机（SAM）": "后缀自动机",
    "字符串哈希/hash": "字符串哈希",
    "hash": "哈希表",
    "并查集（DSU）": "并查集",
    "最小生成树（MST）": "最小生成树",
    "数位动态规划": "数位DP",
    "线性动态规划": "线性DP",
    "四边形优化": "四边形不等式优化",
    "LCA": "最近公共祖先",
    "lca": "最近公共祖先",
    "DSU": "并查集",
    "MST": "最小生成树",
    "SCC": "强连通分量",
    "SAM": "后缀自动机",
    "平衡二叉树": "平衡树",
    "BST": "平衡树",
    "Treap": "平衡树",
    "Splay": "平衡树",
    "替罪羊树": "平衡树",
    "三维几何": "立体几何",
    "球面几何": "立体几何",
    "FFT": "多项式与NTT",
    "NTT": "多项式与NTT",
    "树剖": "树链剖分",
    "重链剖分": "树链剖分",
    "树上路径": "树上路径",
    "树上背包": "树形DP",
    "树上倍增": "倍增",
    "割点": "割点与桥",
    "状态压缩": "状压DP",
    "状态压缩DP": "状压DP",
    "子集DP": "状压DP",
    "枚举因子": "枚举",
    "容斥原理": "容斥",
    "Dijkstra": "最短路",
    "Kruskal": "最小生成树",
    "滑动窗口": "双指针",
    "整数除法": "整除",
    "最长上升子序列": "最长递增子序列",
    "概率": "概率与期望",
    "组合计数": "组合数学",
    "叉积": "叉积与方向",
    "BFS": "DFS/BFS",
    "LCP查询": "LCP",
    "Link-Cut Tree": "动态树",
    "动态树（LCT）": "动态树",
    "矩阵": "矩阵乘法",
    "线性筛": "素数筛",
    "分治NTT": "多项式与NTT",
    "分治卷积": "卷积",
    "集合/有序集合": "集合",
    "DAG": "有向无环图",
    "0/1背包": "背包DP",
    "最小费用流": "最小费用最大流",
    "三维前缀和": "高维前缀和",
    "离线": "离线算法",
    "进位": "进位处理",
    "树的高度": "树高",
    "三分搜索": "三分",
    "流算法": "网络流",
    "最长公共前缀": "LCP",
    "期望": "概率与期望",
    "结论": "数学",
    "Floyd-Warshall": "Floyd",
    "Cartesian Tree": "笛卡尔树",
    "Cartesian tree": "笛卡尔树",
    "线性基（Linear Basis）": "线性基",
    "多项式": "多项式与NTT",
    "换根动态规划": "换根DP",
    "树的直径算法": "树的直径",
    "优先队列": "堆",
    "异或": "位运算",
    "同余": "模运算",
    "图": "图论",
    "李超线段树": "李超树",
    "树分治": "点分治",
    "Trie": "字典树",
    "FFT/NTT": "多项式与NTT",
    "DSU on tree": "启发式合并",
}

_CANONICAL = frozenset(DETAIL_TAG_LABELS)


def normalize_detail_tags(tags: Iterable[object] | None) -> list[str]:
    """Return unique canonical labels in stable input order.

    Unknown names are rejected deliberately.  A typo in a tag should stop a
    data export instead of silently creating a second name for an existing
    knowledge point.
    """

    if tags is None:
        return []
    if isinstance(tags, (str, bytes)):
        raise ValueError("detailTags must be a list")
    result: list[str] = []
    seen: set[str] = set()
    try:
        iterator = iter(tags)
    except TypeError as exc:
        raise ValueError("detailTags must be a list") from exc
    for raw in iterator:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("detailTags entries must be non-empty strings")
        value = raw.strip()
        value = DETAIL_TAG_ALIASES.get(value, value)
        if value not in _CANONICAL:
            raise ValueError(f"unknown detail tag: {raw}")
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def is_canonical_detail_tag(value: object) -> bool:
    return isinstance(value, str) and value in _CANONICAL
