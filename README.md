# xcpc · rating

**在线站点：<https://heimaom.cn/>**

面向 XCPC（ICPC / CCPC / 省赛）**个人选手**的积分与赛事数据站。从 [algoux/srk-collection](https://github.com/algoux/srk-collection) 的官方榜单出发，按时间顺序逐场回放，为每位选手计算可横向比较的积分，生成纯静态网页展示榜单、比赛、选手档案、题型十三维雷达面板等数据。

## 核心特点

- **评分对象是个人**：身份键为规范化的 姓名@学校，团队赛名次按规则分摊到每位队员
- **增量阶梯分体系**：人人从 1400 起步，逐场累积，打平预期不扣分
- **双榜并列**：全部参赛 vs 仅正式参赛，各自独立计算
- **题型十三维面板**：跟踪每位选手在 13 种题型上的能力分布
- **赛前预测**：基于历史积分和奖牌预测即将开赛的比赛排名

## 快速开始

### 环境准备

\\\ash
# 克隆仓库（含数据 submodule）
git clone --recurse-submodules https://github.com/Hei-MaoM/xcpcrating.git
cd xcpcrating

# 如已克隆但缺少 submodule
git submodule update --init --depth 1

# Python 环境（需要 Python 3.8+）
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
\\\

### 数据导出与预览

\\\ash
# 1. 导出前端数据（从历史榜单回放计算积分）
python -m xcpc_rating.export_web \\
  --data vendor/srk-collection/official \\
  --out web/public/data

# 2. 启动前端预览
cd web
npm install
npm run dev

# 浏览器访问 http://localhost:5173
\\\

### 生产构建

\\\ash
# 构建前端静态文件
cd web
npm run build

# 产物位于 web/dist/，可直接部署到任何静态托管服务
\\\

## 一键更新脚本

使用 \scripts/update_data.sh\ 自动完成数据更新、回测、导出和构建：

\\\ash
bash scripts/update_data.sh            # 完整流程
bash scripts/update_data.sh --no-build # 跳过前端构建
\\\

## 项目结构

\\\
xcpcrating/
├── src/xcpc_rating/           # Python 后端（评分引擎、数据导出）
│   ├── engines/              # 评分算法实现
│   ├── model.py              # 数据模型（Contest、Team、Member）
│   ├── loader.py             # 榜单数据加载
│   ├── export_web.py         # 前端数据契约导出
│   └── cli.py                # 命令行工具
├── web/                       # 前端（React + TypeScript + Vite）
│   ├── src/
│   │   ├── pages/            # 页面（榜单、比赛、选手、规则）
│   │   └── lib/              # 数据加载、搜索、可视化
│   └── public/data/          # 导出的 JSON 数据
├── vendor/srk-collection/     # 数据源（git submodule）
├── predictions/               # 赛前预测参赛名单
├── tests/                     # 单元测试
└── scripts/                   # 辅助脚本
\\\

## 评分算法（增量阶梯分）

每位选手维护一个预期水平 E（初始 1400），显示分即 E 本身。每场比赛分两步：

1. **反解表现分**：基于全场排名和队伍强度，使用 Elo 期望名次公式反解每队的表现分
2. **更新积分**：根据表现分调整每位队员的 E 值，达到预期不扣分

### 关键参数

- **比赛权重**：决赛 1.5 / 区域赛 1.3 / 邀请赛 0.8 / 省赛 0.7
- **净注入额**：决赛 20000 / 区域赛 15000 / 邀请赛 10000 / 省赛 0
- **资格门槛**：省赛 <1800 分、邀请赛 <2000 分时计分，区域赛和决赛无限制
- **达预期不扣分**：排名优于预测时调整值取 max(调整, 0)

详细规则请访问网站的「规则」页面。

## 数据来源

- 主数据源：[algoux/srk-collection](https://github.com/algoux/srk-collection)（官方榜单）
- 收录范围：ICPC、CCPC、省赛三类官方比赛
- 同场去重：同一物理比赛的双榜只保留一份（网络预选赛除外）

## 技术栈

**后端**
- Python 3.8+：numpy、pytest
- 评分引擎：Elo 变体、LSE 团队强度聚合

**前端**
- React 18 + TypeScript
- Vite 构建工具
- ECharts 数据可视化
- Web Worker 处理大数据集

**部署**
- GitHub Pages（静态托管）
- 纯前端方案，无服务器依赖

## 开发与贡献

### 运行测试

\\\ash
# Python 单元测试
pytest

# 回测验证（时间序一致性检查）
python -m xcpc_rating validate --data vendor/srk-collection/official
\\\

### 添加赛前预测

在 \predictions/\ 目录创建 \<contest-slug>.json\，格式参考现有文件。

### 数据契约

前端数据格式定义在 \web/public/data/README.md\，修改导出器时请保持兼容性。

## 许可证

MIT License

## 致谢

- 数据源：[algoux/srk-collection](https://github.com/algoux/srk-collection)
- 评分算法灵感：Codeforces rating system

---

**技术文档**：详见 \docs/\ 目录  
**问题反馈**：[GitHub Issues](https://github.com/Hei-MaoM/xcpcrating/issues)
