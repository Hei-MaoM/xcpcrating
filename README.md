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

每位选手内部维护一个预期水平 `E`（初始 1500），显示分从 0 起步逐步逼近 `E`。
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
单场调整  = k × ( 表现分 − 190.85 − E )                # 190.85 = 400×log10(3)，团队→个人尺度偏移
达预期不扣分: 名次 ≤ 预测名次 ⇒ 调整 = max(调整, 0)
步长  k   = min( 0.30 × w × (1 + 1.5×0.5^n + b), 0.85 ) # n=已计分场次；新手/久疏提速
久疏提速 b = 1 − 0.5^((间隔天数 − 200)/180)             # ≤200 天为 0
更新       E ← E + 调整
显示分     = max(0, E − 1500 × 0.4^n)
```

- **比赛权重 w**：决赛 1.5，区域赛 / 邀请赛 / 省赛均 1.0。
- **资格门槛**：省赛仅在 `E < 1950`、邀请赛仅在 `E < 2150` 时计分；区域赛 / 决赛无限制
  （高手赢低级别赛事属预期，不再加分）。
- **奖牌**：按 [standard-ranklist](https://github.com/algoux/standard-ranklist) 规范逐段读取
  金 / 银 / 铜分界，仅统计正式排名；未声明分界时用 ICPC 默认（金=正式人数前 10% 向上取整，
  银 2×、铜 3×）。

网页「规则」页是这套算法的权威说明；改引擎参数时请同步该页。

## 数据来源与口径

- 数据源为 `vendor/srk-collection` submodule（algoux/srk-collection），只读。
- 只计入 `icpc / ccpc / provincial` 三类官方榜单；一场比赛只要至少有 1 行带有效队员名单即计入，
  整场无名单（覆盖率 0）则跳过。无名单的单行作为打星保留在展示中、不参与个人评分。
