import { Link } from 'react-router-dom'
import { RuleDraw } from '../../components/ui'

/**
 * 积分规则页（route: #/rules）。以公式为主说明算法：选手从 1400 起步、逐场累积，
 * 末尾另说明学校榜的贝叶斯零和规则（各校从 1500 起步）。公式中的常量分别与
 * `src/xcpc_rating/engines/incremental.py`（选手）与 `engines/school.py`（学校）
 * 保持一致 —— 调整引擎参数时应同步本页。
 */
export default function RulesPage() {
  return (
    <div className="page-enter rules">
      {/* hero */}
      <section className="wrap phead">
        <span className="eyebrow eyebrow--oxford">计分方法</span>
        <h1 className="display">积分规则</h1>
        <p className="subtle">
          每位选手的积分由历次赛场表现按时间顺序逐场累积而成。下面给出完整的计算公式与边界规则。
        </p>
      </section>

      {/* 计算公式 */}
      <section className="wrap" style={{ paddingTop: 16, paddingBottom: 56 }}>
        <div className="section-label">
          <span className="eyebrow">计算公式</span>
          <RuleDraw className="section-label__rule" />
        </div>

        <p className="rules-lead">
          每场比赛分两步：先由全场名次<strong>反推</strong>出每支队伍的表现分，
          再据此更新每位选手的积分。下式均在 Elo 尺度（400 分一档、对数底 10）下计算。
        </p>

        <p className="formula-cap">① 反推表现分（每队一个）</p>
        <div className="formula-stack">
          <div className="frow">
            <span className="frow__label">队伍强度</span>
            <div className="frow__eq serif">R = 400 × log<sub>10</sub>( Σ 10^(E<sub>k</sub> / 400) )</div>
          </div>
          <div className="frow">
            <span className="frow__label">期望名次</span>
            <div className="frow__eq serif">
              g(R) = 1 + Σ 1 / ( 1 + 10^((R − R<sub>j</sub>) / 400) )，　seed = g(R<sub>本队</sub>)
            </div>
          </div>
          <div className="frow">
            <span className="frow__label">目标名次</span>
            <div className="frow__eq serif">m = √( seed × 实际名次 )</div>
          </div>
          <div className="frow">
            <span className="frow__label">队伍表现分</span>
            <div className="frow__eq serif">P = g<sup>−1</sup>(m)</div>
          </div>
          <div className="frow">
            <span className="frow__label">个人表现分</span>
            <div className="frow__eq serif">
              表现分 = P − 团队偏移　（团队偏移 = 400 × log<sub>10</sub> 队伍人数）
            </div>
          </div>
        </div>

        <p className="formula-cap">② 更新积分（每位队员）</p>
        <div className="formula-stack">
          <div className="frow">
            <span className="frow__label">单场调整</span>
            <div className="frow__eq serif">调整 = k × ( 表现分 − E )</div>
          </div>
          <div className="frow">
            <span className="frow__label">达预期不扣分</span>
            <div className="frow__eq serif">
              名次 ≤ 预测名次　⇒　调整 = max( 调整,&nbsp; 0 )
            </div>
          </div>
          <div className="frow">
            <span className="frow__label">步长 k</span>
            <div className="frow__eq serif">
              k = min( 0.40 × w,&nbsp; 0.85 )
            </div>
          </div>
          <div className="frow">
            <span className="frow__label">防通胀微调</span>
            <div className="frow__eq serif">
              全场调整统一平移并分摊到每位选手：省赛净和 = 0（零和不通胀）；区域赛 / 邀请赛 / 决赛每场额外注入一份净分（决赛最多、区域次之、邀请再次），体现含金量
            </div>
          </div>
          <div className="frow">
            <span className="frow__label">更新</span>
            <div className="frow__eq serif">E ← E + 调整 + 微调</div>
          </div>
          <div className="frow">
            <span className="frow__label">显示分</span>
            <div className="frow__eq serif">显示分 = E　（人人从 1400 起步）</div>
          </div>
        </div>

        <div className="legend-grid">
          <div><b>R</b>队伍强度，由各队员内部分 E<sub>k</sub> 聚合（一支三人新队约 1590.85）</div>
          <div><b>E<sub>k</sub></b>队员内部预期水平 = 显示分，初始 1400</div>
          <div><b>Σ</b>队伍强度对本队队员求和；g(R) 对全场其他队伍求和</div>
          <div><b>R<sub>j</sub></b>全场其他队伍的强度；seed 为期望名次</div>
          <div><b>名次</b>该场实际名次；预测名次按队伍强度降序排定</div>
          <div><b>w</b>比赛权重（决赛 1.5 / 区域赛 1.3 / 邀请赛 0.8 / 省赛 0.7；见下表）</div>
          <div><b>团队偏移</b>= 400 × log<sub>10</sub>(队伍人数)：三人队 190.85 / 两人队 120.4 / 一人队 0</div>
        </div>
      </section>

      {/* 比赛分级 */}
      <section className="band--2">
        <div className="wrap" style={{ paddingTop: 56, paddingBottom: 56 }}>
          <div className="section-label">
            <span className="eyebrow">比赛分级</span>
            <RuleDraw className="section-label__rule" />
          </div>
          <p className="rules-lead">
            比赛按含金量分四档，决定单场调整的速度（公式中的 w）。级别越高牵引越快 ——
            决赛、区域赛的上升与回落都快于邀请赛、省赛，因此高水平选手主要在区域赛 /
            决赛拉开身位，而邀请赛、省赛对积分的影响被刻意调小。
          </p>
          <div className="board-card" style={{ marginTop: 22 }}>
            <table className="tbl">
              <colgroup>
                <col />
                <col style={{ width: '130px' }} />
                <col />
              </colgroup>
              <thead>
                <tr>
                  <th>级别</th>
                  <th className="right">权重 w</th>
                  <th>范围</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><b>决赛</b></td>
                  <td className="right score-strong">1.5×</td>
                  <td className="muted">EC-Final、CCPC 总决赛</td>
                </tr>
                <tr>
                  <td><b>区域赛</b></td>
                  <td className="right score-strong">1.3×</td>
                  <td className="muted">常规 ICPC / CCPC 区域赛站点，以及各赛季网络预选赛</td>
                </tr>
                <tr>
                  <td><b>邀请赛</b></td>
                  <td className="right">0.8×</td>
                  <td className="muted">全国邀请赛</td>
                </tr>
                <tr>
                  <td><b>省赛</b></td>
                  <td className="right">0.7×</td>
                  <td className="muted">各省省赛，以及女生专场 / 高职专场</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* 资格门槛 */}
      <section className="wrap" style={{ paddingTop: 56, paddingBottom: 56 }}>
        <div className="section-label">
          <span className="eyebrow">资格门槛</span>
          <RuleDraw className="section-label__rule" />
        </div>
        <p className="rules-lead">
          当选手内部水平 E 达到一定高度后，低级别比赛不再纳入计分（既不加分亦不扣分），
          亦不计入其成绩记录 —— 高水平选手在低级别赛事中取胜属预期之内。
        </p>
        <div className="board-card" style={{ marginTop: 22 }}>
          <table className="tbl">
            <colgroup>
              <col />
              <col />
            </colgroup>
            <thead>
              <tr>
                <th>比赛级别</th>
                <th>计分条件（按赛前 E 判定）</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><b>省赛</b></td>
                <td className="muted">E &lt; <span className="tnum">1800</span> 时计分</td>
              </tr>
              <tr>
                <td><b>邀请赛</b></td>
                <td className="muted">E &lt; <span className="tnum">2000</span> 时计分</td>
              </tr>
              <tr>
                <td><b>区域赛 · 决赛</b></td>
                <td className="muted">无限制，始终计分</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="rules-lead" style={{ marginTop: 18 }}>
          此外，个别比赛若存在<strong>作弊、假题</strong>等问题，会被整场标记为 <b>unrated</b>：
          榜单与成绩照常展示，但<strong>不参与任何计分</strong>（全场所有人均无积分变动）。
          比赛页顶部会给出说明。
        </p>
      </section>

      {/* 两个榜 */}
      <section className="band--2">
        <div className="wrap" style={{ paddingTop: 56, paddingBottom: 56 }}>
          <div className="section-label">
            <span className="eyebrow">两种榜单口径</span>
            <RuleDraw className="section-label__rule" />
          </div>
          <div className="rules-grid">
            <div className="spec-card">
              <h4 className="spec-card__h">正式参赛</h4>
              <p className="spec-card__p">
                <strong>默认口径</strong>。仅统计正式参赛成绩，打星（非正式排名）场次不予计入。
                选手页该口径下，打星场次不计分、不列出，名次按正式队伍重新计。
              </p>
            </div>
            <div className="spec-card">
              <h4 className="spec-card__h">全部参赛</h4>
              <p className="spec-card__p">
                纳入打星场次，反映选手实际参加的全部比赛。
                两种口径独立计算、各成一榜，可随时切换对照。
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 奖牌 */}
      <section className="wrap" style={{ paddingTop: 56, paddingBottom: 64 }}>
        <div className="section-label">
          <span className="eyebrow">奖牌统计</span>
          <RuleDraw className="section-label__rule" />
        </div>
        <p className="rules-lead">
          奖牌依据 <b>algoux / standard-ranklist</b> 规范逐段读取各场的金 / 银 / 铜分界，仅统计正式排名。
          未声明分界时采用 ICPC 默认：金牌为正式参赛人数前 <span className="tnum">10%</span>（向上取整），
          银牌为金牌数 2 倍、铜牌 3 倍。<strong>网络预选赛是资格赛、不颁奖牌</strong>，因此计分但不计入奖牌统计。
        </p>
      </section>

      {/* 学校榜 */}
      <section className="band--2">
        <div className="wrap" style={{ paddingTop: 56, paddingBottom: 56 }}>
          <div className="section-label">
            <span className="eyebrow">学校榜</span>
            <RuleDraw className="section-label__rule" />
          </div>
          <p className="rules-lead">
            除选手榜外另设<strong>学校榜</strong>，与选手榜相互独立。把每所学校当作一名“选手”，
            用<strong>贝叶斯零和</strong>逐场累积评分 —— 一所学校的强弱看的是它<strong>每一场</strong>相对其他学校的发挥，
            而非靠某位明星选手把分拉高。各校从 <span className="tnum">1500</span> 起步，全场均值恒定。
          </p>

          <p className="formula-cap">① 校排（每场每校取最强一队）</p>
          <div className="formula-stack">
            <div className="frow">
              <span className="frow__label">学校名次</span>
              <div className="frow__eq serif">
                每校只取其<strong>最强一支正式队伍</strong>的名次，再在参赛学校间重排（并列同名次）
              </div>
            </div>
          </div>

          <p className="formula-cap">② 反推表现分（校排 → P）</p>
          <div className="formula-stack">
            <div className="frow">
              <span className="frow__label">学校表现分</span>
              <div className="frow__eq serif">
                以参赛各校当前评分为对手场，按与选手榜相同的名次反推公式求 P（强而深的学校场中夺冠更值钱）
              </div>
            </div>
            <div className="frow">
              <span className="frow__label">表现分封顶</span>
              <div className="frow__eq serif">
                P ≤ 全场<strong>次强学校</strong>评分 + 200，且按名次单调不增（赢弱场刷不出虚高，强弱悬殊的省赛冠亚军不被拉开过大）
              </div>
            </div>
          </div>

          <p className="formula-cap">③ 贝叶斯零和更新（每所学校）</p>
          <div className="formula-stack">
            <div className="frow">
              <span className="frow__label">学习率</span>
              <div className="frow__eq serif">α = 1 / ( κ + n )，　κ = 4，n 为该校累计场次（含本场）</div>
            </div>
            <div className="frow">
              <span className="frow__label">单场调整</span>
              <div className="frow__eq serif">调整 = w × α × ( P − S )</div>
            </div>
            <div className="frow">
              <span className="frow__label">零和微调</span>
              <div className="frow__eq serif">
                微调 = − 全场调整均值　⇒　Σ( 调整 + 微调 ) = 0（只再分配，不通胀）
              </div>
            </div>
            <div className="frow">
              <span className="frow__label">更新</span>
              <div className="frow__eq serif">S ← S + 调整 + 微调</div>
            </div>
          </div>

          <div className="legend-grid">
            <div><b>S</b>学校当前评分，初始 1500；超出表现则升、不及则降</div>
            <div><b>α</b>学习率随场次递减：老牌学校（n 大）单场几乎不动，新学校适应快</div>
            <div><b>κ</b>先验强度 = 4，越大越稳、越向 1500 收敛</div>
            <div><b>n</b>该校累计正式参赛场次（含本场）</div>
            <div><b>w</b>比赛权重（与选手榜不同，见下表）</div>
            <div><b>口径</b>仅正式参赛队伍计入；不足两所学校的场次跳过</div>
          </div>

          <div className="board-card" style={{ marginTop: 22 }}>
            <table className="tbl">
              <colgroup>
                <col />
                <col style={{ width: '130px' }} />
                <col />
              </colgroup>
              <thead>
                <tr>
                  <th>级别</th>
                  <th className="right">学校权重 w</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><b>决赛</b></td>
                  <td className="right score-strong">1.5×</td>
                  <td className="muted">含金量最高，拉开学校身位最快</td>
                </tr>
                <tr>
                  <td><b>区域赛</b></td>
                  <td className="right score-strong">1.0×</td>
                  <td className="muted">基准权重</td>
                </tr>
                <tr>
                  <td><b>邀请赛</b></td>
                  <td className="right">0.8×</td>
                  <td className="muted">略低</td>
                </tr>
                <tr>
                  <td><b>省赛</b></td>
                  <td className="right">0.5×</td>
                  <td className="muted">场子弱、含金量低，对评分牵引最小</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* 结尾 */}
      <section className="wrap" style={{ paddingTop: 24, paddingBottom: 80 }}>
        <div className="rules-end">
          <p>
            数据来源于 <b>algoux / srk-collection</b> 的公开成绩，按时间顺序逐场回放生成。
            如对某场积分变动有疑问，可在选手页查阅逐场明细。
          </p>
          <Link to="/" className="btn">
            查看榜单
          </Link>
        </div>
      </section>
    </div>
  )
}
