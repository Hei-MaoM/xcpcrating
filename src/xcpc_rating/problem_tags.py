"""Canonical names for the fine-grained problem-tag field.

Leaves live in a 13-root tree.  Each root maps onto one of the thirteen public
skill axes, so a placed leaf determines the coarse axis.  ``detailTags``
stores leaf labels only.  A small alias table keeps old hand-entered names
from creating duplicates.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple


class TagGroup(NamedTuple):
    key: str
    label: str
    leaves: tuple[str, ...]


class TagRoot(NamedTuple):
    key: str
    label: str
    axis: str
    blurb: str
    groups: tuple[TagGroup, ...]


TAG_TREE: tuple[TagRoot, ...] = (
    TagRoot(
        key="adhoc",
        label="思维与模拟",
        axis="adhoc",
        blurb="不依赖特定算法的思维题、模拟题、构造题",
        groups=(
            TagGroup(
                key="enumeration-simulation",
                label="枚举与模拟",
                leaves=(
                    "枚举", "模拟", "暴力", "分类讨论", "分段", "打表", "分段打表", "周期性", "周期性引理", "主元素", "康威生命游戏", "约瑟夫问题",
                    "表达式求值", "15-puzzle",
                ),
            ),
            TagGroup(
                key="construction",
                label="构造",
                leaves=(
                    "构造", "交互", "提交答案", "交换与调整", "方案输出",
                ),
            ),
            TagGroup(
                key="greedy",
                label="贪心",
                leaves=(
                    "贪心", "排序", "计数排序", "基数排序", "桶排序", "归并排序", "邻项交换", "反悔贪心",
                ),
            ),
        ),
    ),
    TagRoot(
        key="technique",
        label="基础技巧",
        axis="technique",
        blurb="跨领域通用的基础手段",
        groups=(
            TagGroup(
                key="sequence",
                label="序列技巧",
                leaves=(
                    "前缀和", "差分", "高维前缀和", "双指针", "离散化", "扫描线", "区间", "区间交", "子序列", "逆序对",
                ),
            ),
            TagGroup(
                key="search-approx",
                label="查找与逼近",
                leaves=(
                    "二分查找", "三分", "倍增", "绝对值不等式", "一次函数", "对数比较", "判别式", "单调性",
                ),
            ),
            TagGroup(
                key="bits-numeric",
                label="位与数值",
                leaves=(
                    "位运算", "高精度", "快速幂", "进位处理", "格雷码", "康托展开",
                ),
            ),
            TagGroup(
                key="recurrence",
                label="递推与迭代",
                leaves=(
                    "递推", "迭代", "鸽巢原理", "抽屉原理", "优化",
                ),
            ),
        ),
    ),
    TagRoot(
        key="search",
        label="搜索",
        axis="search",
        blurb="状态空间搜索与剪枝",
        groups=(
            TagGroup(
                key="search",
                label="搜索",
                leaves=(
                    "DFS/BFS", "双向搜索", "折半搜索", "启发式搜索", "A*", "迭代加深", "IDA*", "回溯法", "DLX", "Alpha-Beta剪枝",
                    "剪枝", "状态空间搜索",
                ),
            ),
        ),
    ),
    TagRoot(
        key="offline",
        label="分治与离线",
        axis="offline",
        blurb="按维度拆分或把询问离线处理",
        groups=(
            TagGroup(
                key="divide-conquer",
                label="分治",
                leaves=(
                    "分治", "递归", "CDQ分治", "整体二分", "线段树分治", "分数规划",
                ),
            ),
            TagGroup(
                key="mo",
                label="莫队",
                leaves=(
                    "莫队", "带修改莫队", "树上莫队", "回滚莫队", "二维莫队", "莫队二次离线", "莫队配合bitset",
                ),
            ),
            TagGroup(
                key="offline",
                label="离线",
                leaves=(
                    "离线算法", "扫描线离线", "时间分块",
                ),
            ),
        ),
    ),
    TagRoot(
        key="random",
        label="随机与近似",
        axis="random",
        blurb="随机化、启发式与近似算法",
        groups=(
            TagGroup(
                key="randomized",
                label="随机化",
                leaves=(
                    "随机化", "随机哈希", "随机增量法", "模拟退火", "爬山算法", "遗传算法", "粒子群",
                ),
            ),
            TagGroup(
                key="misc",
                label="杂项",
                leaves=(
                    "珂朵莉树", "悬线法", "Garsia-Wachs算法",
                ),
            ),
        ),
    ),
    TagRoot(
        key="dataStructure",
        label="数据结构",
        axis="dataStructure",
        blurb="维护与查询数据的结构",
        groups=(
            TagGroup(
                key="basic",
                label="基础结构",
                leaves=(
                    "栈", "队列", "双端队列", "单调栈", "单调队列", "链表", "哈希表", "集合", "多重集合", "堆", "优先队列", "可并堆", "左偏树",
                    "配对堆", "环形数组", "动态维护",
                ),
            ),
            TagGroup(
                key="dsu",
                label="并查集",
                leaves=(
                    "并查集", "带权并查集", "可撤销并查集", "按秩合并", "启发式合并",
                ),
            ),
            TagGroup(
                key="fenwick-segtree",
                label="树状数组与线段树",
                leaves=(
                    "树状数组", "线段树", "权值线段树", "动态开点线段树", "线段树合并", "线段树分裂", "李超树", "猫树", "SegmentTreeBeats",
                    "划分树", "二维数点", "区间历史最值", "线段树优化建图",
                ),
            ),
            TagGroup(
                key="balanced-tree",
                label="平衡树",
                leaves=(
                    "平衡树", "Treap", "Splay", "替罪羊树", "笛卡尔树", "跳表", "霍夫曼树", "树堆",
                ),
            ),
            TagGroup(
                key="sqrt",
                label="分块与根号",
                leaves=(
                    "分块", "根号分治", "块状链表", "树分块", "SqrtTree", "值域分块",
                ),
            ),
            TagGroup(
                key="persistent",
                label="可持久化",
                leaves=(
                    "可持久化", "主席树", "可持久化平衡树", "可持久化字典树", "可持久化并查集", "可持久化可并堆",
                ),
            ),
            TagGroup(
                key="advanced",
                label="高级结构",
                leaves=(
                    "树套树", "KD-Tree", "ST表", "RMQ", "动态树", "LCT", "全局平衡二叉树", "欧拉序树", "TopTree", "析合树",
                    "点分树", "树哈希", "树同构", "数据结构", "并查集重构树",
                ),
            ),
        ),
    ),
    TagRoot(
        key="graph",
        label="图论",
        axis="graph",
        blurb="图上的结构与算法",
        groups=(
            TagGroup(
                key="basics",
                label="图论基础",
                leaves=(
                    "图论", "建图", "分层图", "网格图", "连通性", "判环", "负环", "最长路", "对偶图", "拓扑排序", "有向无环图", "拆点", "补图",
                ),
            ),
            TagGroup(
                key="shortest-path",
                label="最短路",
                leaves=(
                    "最短路", "Dijkstra", "Bellman-Ford", "SPFA", "Floyd", "Johnson", "差分约束", "k短路", "同余最短路",
                ),
            ),
            TagGroup(
                key="spanning-tree",
                label="生成树",
                leaves=(
                    "最小生成树", "最小树形图", "最小直径生成树", "生成树计数", "矩阵树定理", "Prüfer序列", "Kruskal重构树",
                ),
            ),
            TagGroup(
                key="connectivity",
                label="连通性",
                leaves=(
                    "强连通分量", "双连通分量", "割点与桥", "圆方树", "点边连通度", "2-SAT", "欧拉回路", "哈密顿回路", "最小环", "环计数",
                ),
            ),
            TagGroup(
                key="tree",
                label="树上问题",
                leaves=(
                    "树", "树的直径", "树的重心", "树的中心", "最近公共祖先", "树链剖分", "长链剖分", "树上差分", "树上路径", "虚树", "点分治",
                    "树高", "树上随机游走", "树的重构",
                ),
            ),
            TagGroup(
                key="other",
                label="其他图论",
                leaves=(
                    "支配树", "斯坦纳树", "平面图", "弦图", "图的着色", "最大团", "LGV引理", "图上随机游走", "最小支配集", "竞赛图", "二分图判定",
                ),
            ),
        ),
    ),
    TagRoot(
        key="flow",
        label="网络流与匹配",
        axis="flow",
        blurb="流量与匹配类模型",
        groups=(
            TagGroup(
                key="network-flow",
                label="网络流",
                leaves=(
                    "网络流", "最大流", "最小割", "最小费用最大流", "上下界网络流", "Stoer-Wagner", "最大权闭合子图", "二分图最小点覆盖",
                    "最小路径覆盖",
                ),
            ),
            TagGroup(
                key="matching",
                label="匹配",
                leaves=(
                    "匹配", "二分图", "二分图匹配", "二分图最大权匹配", "一般图匹配", "一般图最大权匹配", "稳定匹配", "霍尔定理", "KM算法",
                ),
            ),
        ),
    ),
    TagRoot(
        key="dp",
        label="动态规划",
        axis="dp",
        blurb="状态设计与转移优化",
        groups=(
            TagGroup(
                key="basic",
                label="基础DP",
                leaves=(
                    "动态规划", "线性DP", "递推DP", "记忆化搜索", "DAG上DP", "背包DP", "区间DP", "树形DP", "状压DP", "数位DP",
                    "插头DP", "轮廓线DP", "计数DP", "概率DP", "动态DP", "DP套DP", "换根DP", "博弈DP", "最长递增子序列", "最长公共子序列",
                    "最大子段和",
                ),
            ),
            TagGroup(
                key="optimization",
                label="DP优化",
                leaves=(
                    "单调队列优化", "斜率优化", "四边形不等式优化", "SlopeTrick", "WQS二分", "决策单调性", "状态设计优化", "凸函数优化",
                    "矩阵优化DP", "数据结构优化DP", "滚动数组",
                ),
            ),
        ),
    ),
    TagRoot(
        key="string",
        label="字符串",
        axis="string",
        blurb="串的匹配、结构与自动机",
        groups=(
            TagGroup(
                key="basics",
                label="字符串基础",
                leaves=(
                    "字符串", "字符串匹配", "字符串哈希", "KMP", "Z函数", "最小表示法", "LCP", "最长公共子串", "字符串周期", "括号序列",
                ),
            ),
            TagGroup(
                key="suffix",
                label="后缀结构",
                leaves=(
                    "后缀数组", "后缀自动机", "广义后缀自动机", "后缀树", "后缀平衡树", "Lyndon分解", "Main-Lorentz", "Boyer-Moore",
                ),
            ),
            TagGroup(
                key="automaton",
                label="自动机",
                leaves=(
                    "AC自动机", "Fail树", "字典树", "序列自动机", "自动机", "子序列自动机",
                ),
            ),
            TagGroup(
                key="palindrome",
                label="回文",
                leaves=(
                    "回文算法", "Manacher", "回文自动机", "回文串", "双回文串",
                ),
            ),
        ),
    ),
    TagRoot(
        key="math",
        label="数学",
        axis="math",
        blurb="数论、多项式、组合、线代与数值",
        groups=(
            TagGroup(
                key="number-theory",
                label="数论",
                leaves=(
                    "数论", "模运算", "素数", "素数筛", "素数计数", "最大公约数", "扩展欧几里得", "欧拉函数", "质因数分解", "模逆元", "线性同余方程",
                    "同余", "中国剩余定理", "卢卡斯定理", "扩展卢卡斯", "二次剩余", "原根", "离散对数", "升幂引理", "阶乘取模", "费马小定理与欧拉定理",
                    "整除", "整除分块", "数论分块", "类欧几里得", "连分数", "Stern-Brocot树", "二次域", "Pell方程", "狄利克雷卷积",
                    "莫比乌斯反演", "杜教筛", "Min_25筛", "洲阁筛", "PowerfulNumber筛", "高次剩余", "单位根", "反素数", "积性函数",
                    "欧拉降幂",
                ),
            ),
            TagGroup(
                key="polynomial",
                label="多项式与生成函数",
                leaves=(
                    "多项式与NTT", "FWT", "子集卷积", "卷积", "ChirpZ变换", "多项式牛顿迭代", "多项式多点求值与插值", "多项式初等函数",
                    "多项式复合与复合逆", "多项式平移", "线性递推", "Berlekamp-Massey", "拉格朗日插值", "拉格朗日反演", "生成函数", "指数生成函数",
                    "分治NTT", "下降幂", "形式幂级数",
                ),
            ),
            TagGroup(
                key="combinatorics",
                label="组合数学",
                leaves=(
                    "组合数学", "排列", "计数", "容斥", "二项式反演", "Min-Max容斥", "子集枚举", "卡特兰数", "斯特林数", "贝尔数", "错位排列",
                    "伯努利数", "分拆数", "范德蒙德卷积", "Polya计数", "Burnside引理", "图论计数", "斐波那契", "整数拆分", "格路计数",
                    "反射原理",
                ),
            ),
            TagGroup(
                key="linear-algebra",
                label="线性代数",
                leaves=(
                    "线性代数", "矩阵乘法", "矩阵快速幂", "矩阵求逆", "高斯消元", "行列式", "线性基", "特征多项式", "张量", "异或线性基",
                ),
            ),
            TagGroup(
                key="numeric",
                label="数值与优化",
                leaves=(
                    "凸函数", "牛顿迭代", "自适应辛普森", "单纯形", "线性规划", "格林公式", "群论", "拟阵", "拟阵交", "序理论", "杨表",
                    "Schreier-Sims", "数学", "数论变换",
                ),
            ),
        ),
    ),
    TagRoot(
        key="probability",
        label="概率与博弈",
        axis="probability",
        blurb="随机过程的期望与对抗决策",
        groups=(
            TagGroup(
                key="expectation",
                label="概率与期望",
                leaves=(
                    "概率与期望", "马尔可夫链", "鞅", "随机游走期望", "条件期望", "概率生成函数",
                ),
            ),
            TagGroup(
                key="game",
                label="博弈论",
                leaves=(
                    "博弈论", "SG函数", "纳什均衡", "威佐夫博弈", "阶梯博弈", "反Nim", "对抗搜索", "组合博弈",
                ),
            ),
        ),
    ),
    TagRoot(
        key="geometry",
        label="计算几何",
        axis="geometry",
        blurb="平面与空间中的几何对象",
        groups=(
            TagGroup(
                key="basics",
                label="计算几何基础",
                leaves=(
                    "几何", "计算几何", "立体几何", "叉积与方向", "极角排序", "点包含判定", "曼哈顿距离", "Pick定理", "三角剖分", "平面最近点对",
                    "距离", "分数坐标", "精度处理",
                ),
            ),
            TagGroup(
                key="convex",
                label="凸性与变换",
                leaves=(
                    "凸包", "旋转卡壳", "半平面交", "反演变换", "最小圆覆盖", "闵可夫斯基和", "凸多边形交", "扫描线几何", "三维凸包",
                ),
            ),
        ),
    ),
)

DETAIL_TAG_LABELS = tuple(
    leaf for root in TAG_TREE for group in root.groups for leaf in group.leaves
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
    "三维几何": "立体几何",
    "球面几何": "立体几何",
    "FFT": "多项式与NTT",
    "NTT": "多项式与NTT",
    "树剖": "树链剖分",
    "重链剖分": "树链剖分",
    "树上背包": "树形DP",
    "树上倍增": "倍增",
    "割点": "割点与桥",
    "状态压缩": "状压DP",
    "状态压缩DP": "状压DP",
    "子集DP": "状压DP",
    "枚举因子": "枚举",
    "容斥原理": "容斥",
    "Kruskal": "最小生成树",
    "滑动窗口": "双指针",
    "整数除法": "整除",
    "最长上升子序列": "最长递增子序列",
    "概率": "概率与期望",
    "组合计数": "组合数学",
    "叉积": "叉积与方向",
    "BFS": "DFS/BFS",
    "LCP查询": "LCP",
    "Link-Cut Tree": "LCT",
    "动态树（LCT）": "LCT",
    "矩阵": "矩阵乘法",
    "线性筛": "素数筛",
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
    "异或": "位运算",
    "图": "图论",
    "李超线段树": "李超树",
    "树分治": "点分治",
    "Trie": "字典树",
    "FFT/NTT": "多项式与NTT",
    "DSU on tree": "启发式合并",
    "函数式线段树": "主席树",
    "可持久化线段树": "主席树",
    "舞蹈链": "DLX",
    "CDQ": "CDQ分治",
    "Dijkstra算法": "Dijkstra",
    "Manacher算法": "Manacher",
    "CRT": "中国剩余定理",
    "中国剩余": "中国剩余定理",
    "ST 表": "ST表",
    "稀疏表": "ST表",
    "主席树（可持久化线段树）": "主席树",
}


def _index_tree() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    axis: dict[str, str] = {}
    root: dict[str, str] = {}
    group: dict[str, str] = {}
    for item in TAG_TREE:
        for tag_group in item.groups:
            for leaf in tag_group.leaves:
                if leaf in axis:
                    raise ValueError(f"duplicate detail tag: {leaf}")
                axis[leaf] = item.axis
                root[leaf] = item.key
                group[leaf] = tag_group.key
    return axis, root, group


DETAIL_TAG_AXIS, DETAIL_TAG_ROOT, DETAIL_TAG_GROUP = _index_tree()
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


def detail_tag_axis(label: str) -> str | None:
    return DETAIL_TAG_AXIS.get(label)


def detail_tag_root(label: str) -> str | None:
    return DETAIL_TAG_ROOT.get(label)


def axes_for_detail_tags(tags: Iterable[str]) -> list[str]:
    """Unique model axes for canonical leaves, in first-seen order."""

    ordered: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        axis = DETAIL_TAG_AXIS.get(tag)
        if axis is None or axis in seen:
            continue
        ordered.append(axis)
        seen.add(axis)
    return ordered

def labels_from_detail_tags(tags: Iterable[str]) -> dict[str, float]:
    """Coarse-axis weights from leaf counts.  No axis-count cap."""

    counts: dict[str, int] = {}
    for tag in tags:
        value = tag.strip() if isinstance(tag, str) else ''
        value = DETAIL_TAG_ALIASES.get(value, value)
        axis = DETAIL_TAG_AXIS.get(value)
        if axis is None:
            continue
        counts[axis] = counts.get(axis, 0) + 1
    total = sum(counts.values())
    if not total:
        return {}
    return {axis: n / total for axis, n in counts.items()}
