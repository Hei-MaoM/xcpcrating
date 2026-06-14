# xcpc · rating

面向 XCPC（ICPC / CCPC / 省赛）**个人选手**的积分与赛事数据站。从
[algoux/srk-collection](https://github.com/algoux/srk-collection) 的官方榜单出发，
按时间顺序逐场回放，给每位选手算出一个可横向比较的积分，并生成一个纯静态网页
（榜单、比赛、选手档案、积分规则）。

- **评分对象是个人**，不是队伍：身份键为规范化的 `姓名@学校`，教练 / 领队不计入；
  团队赛名次按规则分摊到每位队员。
- **只有一个评分体系**：incremental 阶梯分（“从 0 起步，逐场累积”），不显示不确定度。
- **两个榜并列**：`全部参赛` 与 `仅正式参赛`（打星 / 非正式排名不计入），各自独立计算。

> Python 包名 `xcpc_rating`；站点展示名 **xcpc · rating**。

## 快速开始

```bash
# 1) 克隆（含数据 submodule vendor/srk-collection）
git clone --recurse-submodules <repo-url> rating
cd rating
# 已克隆但忘了 submodule：
git submodule update --init --depth 1

# 2) Python 环境
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # numpy / pytest /（可选 scipy）

# 3) 导出前端数据（按时间序回放，无前瞻泄漏）
PYTHONPATH=src .venv/bin/python -m xcpc_rating.export_web \
  --data vendor/srk-collection/official \
  --out  web/public/data

# 4) 本地预览网页
cd web
npm install
npm run dev          # 开发服务器（HMR）
# 或：npm run build && npm run preview
```

导出产物（`web/public/data/`）：`meta.json`、`contests-index.json`、
`contests/<slug>.json`、`players-index.json`、`players/<shard>.json`、
`leaderboard.json`（全部参赛）、`leaderboard_official.json`（仅正式参赛）。

### 一键更新

`scripts/update_data.sh` 串起“更新数据 → 回测 → 导出 → 构建”：

```bash
bash scripts/update_data.sh            # 完整流程
bash scripts/update_data.sh --no-build # 跳过前端构建
```

它默认拉取 `vendor/srk-collection` submodule 的上游最新提交；可用 `--data-home`
或环境变量 `SRK_DATA_HOME` 指向外部 clone。

## 项目结构

```text
rating/
├── src/xcpc_rating/             # Python 管线
│   ├── model.py                # 数据契约 dataclass（Member / Team / Contest）
│   ├── identity.py             # 姓名/学校规范化、教练剔除、player key
│   ├── loader.py               # 扫描 + 解析 srk 文件 → Contest 列表
│   ├── tier.py                 # 比赛分级（决赛 / 区域赛 / 邀请赛 / 省赛）
│   ├── perf.py                 # 表现分核心：LSE 团队强度 + Elo 期望名次 + 反解
│   ├── engines/
│   │   ├── base.py             # RatingEngine 抽象基类 + PlayerRating
│   │   └── incremental.py      # 唯一评分引擎：阶梯分
│   ├── medals.py               # 奖牌统计（standard-ranklist 规范）
│   ├── validate.py             # 时间序回测框架 + 指标（concordance/spearman）
│   ├── report.py               # 榜单 / 对比报告（CLI 用）
│   ├── export_web.py           # 导出前端 JSON 契约（两个榜 + 逐场轨迹）
│   └── cli.py / __main__.py    # python -m xcpc_rating（回放 + 回测 + 报告）
├── scripts/
│   └── update_data.sh          # 一键更新数据并重跑管线
├── tests/                      # pytest（AAA 结构）
├── vendor/srk-collection/      # 数据源（git submodule，只读）
├── web/                        # 静态数据站（Vite + React + TS）
│   ├── src/pages/              # leaderboard / contests / player / rules
│   ├── src/lib/data.ts         # 导出契约的 TS 镜像（单一事实源）
│   └── public/data/            # 导出器产出的 JSON（构建时打包）
└── .github/workflows/pages.yml # GitHub Pages 部署
```

## 评分算法（incremental 阶梯分）

每位选手内部维护一个预期水平 `E`（初始 1400），显示分即 `E` 本身（人人从 1400 起步）。
每场比赛分两步：先由全场名次**反解**出每队的表现分，再据此更新每位队员。

**① 反解表现分**（Elo 尺度 400、底 10；`Σ` 对全场其他队伍求和）

```
队伍强度  R   = 400 × log10( Σ 10^(E_k / 400) )      # 队员 E 的 LSE 聚合
期望名次  g(R)= 1 + Σ 1 / (1 + 10^((R − R_j)/400)) ，  seed = g(R)
目标名次  m   = √( seed × 实际名次 )
表现分        = g⁻¹(m)                                 # g 单调递减，二分求解
```

**② 更新积分**（每位队员）

```
个人表现分 = 队伍表现分 − 团队偏移                      # 团队偏移 = 400×log10(队伍人数)
单场调整  = k × ( 个人表现分 − E )
达预期不扣分: 名次 ≤ 预测名次 ⇒ 调整 = max(调整, 0)
步长  k   = min( 0.40 × w, 0.85 )                       # w=比赛权重
防通胀微调 = 把全场调整统一平移分摊到每位选手，使本场净和 = 该档目标注入额
更新       E ← E + 调整 + 微调
显示分     = E                                          # 人人从 1400 起步
```

- **比赛权重 w**：决赛 1.5 / 区域赛 1.3 / 邀请赛 0.8 / 省赛 0.7。高档单场牵引更快、更能拉开档次。
- **每场净注入额**：决赛 20000 / 区域赛 15000 / 邀请赛 10000 / 省赛 0（全场均摊到每人）。
  省赛为零和（全体平均分恒守恒于 1400，打平预期不亏不赚），高档注入正分以体现含金量。
- **资格门槛**：省赛仅在 `E < 1800`、邀请赛仅在 `E < 2000` 时计分；区域赛 / 决赛无限制
  （高手赢低级别赛事属预期，不再加分）。
- **个别比赛 unrated**：存在作弊 / 假题的比赛整场不参与计分（榜单照常展示）。
- **奖牌**：按 [standard-ranklist](https://github.com/algoux/standard-ranklist) 规范逐段读取
  金 / 银 / 铜分界，仅统计正式排名；未声明分界时用 ICPC 默认（金=正式人数前 10% 向上取整，
  银 2×、铜 3×）。**网络预选赛是资格赛、不发奖牌**，故不参与奖牌统计。

网页「规则」页是这套算法的权威说明；改引擎参数时请同步该页。

## 数据来源与口径

- 主数据源为 `vendor/srk-collection` submodule（algoux/srk-collection）。
- 此外 12 场**网络预选赛**（2022–2025 的 ICPC / CCPC 在线预选）上游 submodule 没有，
  由爬虫抓取后以标准 srk 存放在仓库内 `srk-extra/official/`（纳入版本管理）：
  `scripts/pta_to_srk.py <pintia-rankings-id>`（pintia）与
  `scripts/xcpcio_to_srk.py <xcpcio-board-path>`（xcpcio）。导出前 `srk-extra/official/`
  会被叠加进 srk-collection 的 `official/`（本地见 `scripts/update_data.sh`、CI 见
  `.github/workflows/pages.yml`），故本地与线上口径一致。
- 只计入 `icpc / ccpc / provincial` 三类官方榜单；一场比赛只要至少有 1 行带有效队员名单即计入，
  整场无名单（覆盖率 0）则跳过。无名单的单行作为打星保留在展示中、不参与个人评分。
- **同场去重**：同一物理比赛的双榜（如邀请赛 + 省赛切片，同日、队员高度重叠）只保留一份。
  网络预选赛是全国性资格赛、与同期线下赛队员大量重叠，**不参与去重**（按区域赛单独计分）。
