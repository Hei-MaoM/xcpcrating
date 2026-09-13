/*
 * Data layer: the complete TypeScript shape of the export contract plus a
 * cached fetch layer. The exporter (`src/xcpc_rating/export_web.py`) is the
 * single source of truth for these field names — this file must not drift.
 *
 * The site presents two leaderboards produced by the single scoring rule (the
 * incremental ladder): an all-participation board and an official-only board.
 *
 * All assets live under `<base>/data/`. Vite's `import.meta.env.BASE_URL`
 * resolves the configured `base: './'` correctly for both Pages and local
 * static serving.
 */

import { shardForKey } from './md5'
import { decodeSkillLeaderboardRows } from './skillLeaderboardCodec'
import {
  decodePlayerSearchRows,
  filterPlayerSearchEntries,
  looksLikePinyinQuery,
  playerSearchShard,
  type PlayerSearchEntry,
  type PlayerSearchRow,
} from './search'

/* ------------------------------------------------------------------ *
 * meta.json
 * ------------------------------------------------------------------ */

export interface MetaCounts {
  contests: number
  archiveContests?: number
  players: number
  ratedPlayers: number
  predictions?: number
}

export interface Meta {
  generatedAt: string
  /** Provenance only ("incremental"); never shown in the UI. */
  engine: string
  counts: MetaCounts
  skillScoreScale?: 'rating' | 'percent'
  dataSource?: {
    repository: string
    commit: string
    sourceBoards: number
    scoringContests: number
    archiveContests: number
    deduplicatedBoards: number
  }
}

/* ------------------------------------------------------------------ *
 * contests-index.json
 * ------------------------------------------------------------------ */

export interface Champion {
  name: string
  org: string
}

export interface ContestStrengthScores {
  bronze: number | null
  silver: number | null
  gold: number | null
  top3: number | null
  top10: number | null
  overall: number | null
}

export interface ContestMedalCutoffs {
  gold: number
  silver: number
  bronze: number
}

export interface ContestMetrics {
  version: string
  /** False when the source has no explicit medal data or for online preliminaries. */
  awardsMedals: boolean
  /** All official participating teams used as equal-weight strength samples. */
  effectiveTeamCount: number
  /** Strength samples with no member carrying pre-contest official history. */
  zeroHistoryTeamCount: number
  /** Strength samples with one or two members carrying pre-contest history. */
  partialHistoryTeamCount: number
  /** Teams whose three members all carry pre-contest history; used by weirdness. */
  weirdnessTeamCount: number
  /** Complete-history teams among all strength samples, in [0, 1]. */
  historyCoverage: number
  medalCutoffs: ContestMedalCutoffs
  /** Six pre-contest team-rating values; compare only within one Sep–Aug season. */
  strength: ContestStrengthScores
  /** Prediction/result divergence on a 0–100 scale; null when undefined. */
  weirdness: number | null
}

export interface ContestIndexEntry {
  id: string
  slug: string
  title: string
  startAt: string
  category: string
  tier: MedalTier
  onlinePreliminary: boolean
  teamCount: number
  champion: Champion
  /** Displayed without rating updates, including archives without a roster. */
  unrated?: boolean
  archiveOnly?: boolean
  /** Absent in legacy exports generated before contest metrics were introduced. */
  contestMetrics?: ContestMetrics
}

/* ------------------------------------------------------------------ *
 * contests/<slug>.json
 * ------------------------------------------------------------------ */

export interface TeamMember {
  key: string
  name: string
}

export interface ContestTeam {
  rank: number
  name: string
  org: string
  solved: number
  penalty: number
  official: boolean
  members: TeamMember[]
  /**
   * Pre-contest predicted rank (1-based). Null for a non-participated row (a
   * 0-submission team is displayed but never scored), so read defensively.
   */
  predictedRank: number | null
  /** This contest's shared performance score; null for a non-participated row. */
  perf: number | null
  /**
   * Pre-contest display rating for the team. Null when the team has no rated
   * history yet, or absent in a regenerating export — read defensively and
   * coalesce missing to null.
   */
  preRating: number | null
  /**
   * Average change in the team members' internal expectation E from this
   * contest. Null for ghost/unrated teams, or absent in a regenerating export
   * — read defensively and coalesce missing to null.
   */
  muDelta: number | null
  /**
   * Official-only 口径 counterparts (field excludes 打星 teams). Null for a 打星
   * team, which the 仅正式 view hides. The contest page swaps to these when the
   * 仅正式 caliber is active.
   */
  predictedRankOfficial: number | null
  perfOfficial: number | null
  preRatingOfficial: number | null
  muDeltaOfficial: number | null
  /** Rank among official teams only (1224 over the official subset). */
  rankOfficial: number | null
  /** Members (0–3) with official rating history before this contest. */
  knownMembersOfficial: number | null
}

export type ContestProblemStatus = 'classified' | 'unknown' | 'conflict'
export type ContestProblemDifficultyKey =
  | 'veryEasy'
  | 'easy'
  | 'easyMid'
  | 'mid'
  | 'midHard'
  | 'hard'
  | 'veryHard'
  | 'unknown'

/** Problem-level metadata joined from the raw contest and the type manifest. */
export interface ContestProblem {
  alias: string
  title: string | null
  canonicalId: string | null
  /** Public statement or contest URL for the problem, when available. */
  problemUrl?: string | null
  typeKeys: SkillAxisKey[]
  typeLabels: string[]
  /** Canonical fine-grained algorithm labels; one name per knowledge point. */
  detailTags?: string[]
  status: ContestProblemStatus
  confidence: number
  accepted: number | null
  submitted: number | null
  eligibleTeams: number
  /** Smoothed expected solve rate, not the player's own result. */
  solveRate: number | null
  problemRating: number | null
  posteriorSd: number | null
  ratingSampleCount: number
  /** Sum of observation weights after down-weighting no-attempt rows. */
  ratingEffectiveSampleCount: number
  ratingAcCount: number
  expectedPassRateAtReference: number | null
}

export interface ContestDetail {
  id: string
  slug: string
  title: string
  startAt: string
  category: string
  tier: MedalTier
  onlinePreliminary: boolean
  teamCount: number
  /** Pre-contest prediction hit-rate for this contest; null when undefined. */
  concordance: number | null
  /** Displayed without rating updates, including archives without a roster. */
  unrated?: boolean
  archiveOnly?: boolean
  /** Reason shown on the contest page when unrated. */
  unratedNote?: string | null
  /** Absent in legacy exports generated before contest metrics were introduced. */
  contestMetrics?: ContestMetrics
  /** Absent in legacy exports without problem-level metadata. */
  problems?: ContestProblem[]
  teams: ContestTeam[]
}

/* ------------------------------------------------------------------ *
 * predictions-index.json + predictions/<slug>.json
 * ------------------------------------------------------------------ */

export interface PredictionIndexEntry {
  id: string
  slug: string
  title: string
  shortTitle: string
  startAt: string | null
  category: string
  teamCount: number
  officialTeamCount: number
  starredTeamCount: number
  totalMembers: number
  matchedMembers: number
}

export interface PredictionMember {
  key: string
  name: string
  matched: boolean
  matchedOfficial: boolean
  rating: number
  officialRating: number
}

export interface PredictionTeam {
  number: number
  name: string
  org: string
  seat: string
  official: boolean
  members: PredictionMember[]
  matchedMembers: number
  matchedOfficialMembers: number
  allStrength: number
  officialStrength: number
  allRank: number
  officialRank: number | null
  historicalMedals?: {
    gold: number
    silver: number
    bronze: number
  }
  historicalMedalsByTier?: Record<
    'final' | 'regional' | 'invitational' | 'provincial',
    {
      gold: number
      silver: number
      bronze: number
    }
  >
  medalRank?: number | null
}

export interface PredictionSchool {
  rank: number
  org: string
  teamNumber: number
  teamName: string
  strength: number
  award: string | null
}

export interface PredictionPrize {
  schoolBestTeamOnly?: boolean
  eligibleScope?: string
  awards?: Array<{ label: string; count: number }>
}

export interface PredictionDetail extends PredictionIndexEntry {
  source: string
  sourceDate: string | null
  ratingCutoff: string
  ratedContestCount: number
  officialMembers: number
  matchedOfficialMembers: number
  priorRating: number
  prize: PredictionPrize
  schools: PredictionSchool[]
  teams: PredictionTeam[]
  notes: string[]
}

/* ------------------------------------------------------------------ *
 * players/<shard>.json
 * ------------------------------------------------------------------ */

export interface PlayerHistoryEntry {
  /** contestId is the slug. */
  contestId: string
  title: string
  startAt: string
  teamName: string
  rank: number
  teamCount: number
  /**
   * Whether the player was officially ranked here (false = 打星 / 非正式). Drives
   * the 正式参赛 view: a starred row is still shown, but its score columns render
   * "—". Defaults to true when absent (older export).
   */
  official: boolean
  /**
   * Whether this contest counted toward the all-participation ladder. A gated-out
   * (display-only) contest is unrated; its score columns render "—". Defaults to
   * true when absent.
   */
  rated: boolean
  /** Whether this contest counted toward the official-only ladder. */
  ratedOfficial: boolean
  perf: number
  /** Display ladder rating after this contest; null if not exported. */
  rating_after: number | null
  /** Internal expectation E after this contest (smooth chart line); null if absent. */
  mu_after: number | null
  /**
   * Official-only board's perf for this contest (field excludes 打星 teams), or
   * null when the player was starred here (no official row) or unscored.
   */
  perfOfficial: number | null
  /** Official-only board display rating after this contest; null when starred. */
  ratingAfterOfficial: number | null
  /** Official-only board internal E after this contest; null when starred. */
  muAfterOfficial: number | null
  /** Rank among official teams only (1224 over the official subset); null when starred. */
  rankOfficial: number | null
  /** Official team count for this contest (the 正式参赛 name次 denominator); null when starred. */
  teamCountOfficial: number | null
}

export interface PlayerDetail {
  key: string
  name: string
  org: string
  contests: number
  /** Display ladder rating; null when unrated or not yet exported. */
  rating: number | null
  /** Precomputed standings (so the player page needs no leaderboard fetch). */
  allRank: number | null
  officialRank: number | null
  officialRating: number | null
  /**
   * Tiered gold/silver/bronze medals, keyed by prestige tier. Optional and
   * Partial: the exporter omits the field entirely for medal-less players and
   * omits any zero-medal tier, so a player with no medals simply has no
   * `medals` key — read defensively.
   */
  medals?: PlayerMedals
  /** Per-tier problem-type skill profile. Optional until the taxonomy bundle is deployed. */
  skillPanel?: PlayerSkillPanel
  history: PlayerHistoryEntry[]
}

/* ------------------------------------------------------------------ *
 * Tiered medals (gold / silver / bronze, bucketed by contest prestige)
 * ------------------------------------------------------------------ */

/**
 * Prestige tiers the exporter buckets medals into, mirroring the Python
 * `tier.classify_tier` values: final / regional / invitational / provincial.
 * The UI renders them in this display order (most to least prestigious).
 */
export type MedalTier = 'final' | 'regional' | 'invitational' | 'provincial'
export type PanelScope = 'overall'

/** Display order for medal tiers (most prestigious first). */
export const MEDAL_TIER_ORDER: readonly MedalTier[] = [
  'final',
  'regional',
  'invitational',
  'provincial',
]

/** Five-dimension rating badge, including the composite top-ten surprises. */
export type PanelGrade = 'SSS' | 'SS' | 'S' | 'A' | 'B' | 'C' | 'D' | 'E' | 'F'

export type PanelMetricKey =
  | 'avgAc'
  | 'dirt'
  | 'rankPercent'
  | 'firstATime'
  | 'lastHourSolved'

export interface PlayerPanelMetric {
  value: number | null
  /** Mid-rank percentile in the same tier cohort; a smaller number is better. */
  topPercent: number | null
  grade: PanelGrade | null
  /** Contest count that supplied this metric (missing raw detail is excluded). */
  validContests: number
}

export interface PlayerPanelOverall {
  topPercent: number
  grade: PanelGrade
  rank: number
  total: number
  validMetrics: number
}

export interface PlayerPanelTier {
  contests: number
  metrics: Record<PanelMetricKey, PlayerPanelMetric>
  overall: PlayerPanelOverall | null
}

export type PlayerPanelMode = Partial<Record<MedalTier | PanelScope, PlayerPanelTier>>

export interface PlayerPanel {
  all: PlayerPanelMode
  official: PlayerPanelMode
}

/** Compact wire format stored in player shards; expanded after fetch. */
export type PlayerPanelMetricRaw = [
  value: number | null,
  topPercent: number | null,
  grade: PanelGrade | null,
  validContests: number,
]

export type PlayerPanelOverallRaw = [
  topPercent: number,
  grade: PanelGrade,
  rank: number,
  total: number,
  validMetrics: number,
]

export type PlayerPanelTierRaw = [
  contests: number,
  metrics: PlayerPanelMetricRaw[],
  overall: PlayerPanelOverallRaw | null,
]

export type PlayerPanelModeRaw = Partial<Record<MedalTier | PanelScope, PlayerPanelTierRaw>>

export interface PlayerPanelRaw {
  all: PlayerPanelModeRaw
  official: PlayerPanelModeRaw
}

export type SkillAxisKey =
  | 'dataStructure'
  | 'graph'
  | 'dp'
  | 'math'
  | 'string'
  | 'geometry'
  | 'basic'

export const SKILL_AXIS_ORDER: readonly SkillAxisKey[] = [
  'dataStructure',
  'graph',
  'dp',
  'math',
  'string',
  'geometry',
  'basic',
]

export const SKILL_AXIS_LABELS: Record<SkillAxisKey, string> = {
  dataStructure: '数据结构',
  graph: '图论与网络',
  dp: '动态规划',
  math: '数学',
  string: '字符串',
  geometry: '几何',
  basic: '基础算法',
}

export interface PlayerSkillAxis {
  /** Original ability rating, on the problem-rating scale; null when absent. */
  score: number | null
  /** Calibrated posterior mastery, relative to the cohort's expected difficulty. */
  mastery: number | null
  topPercent: number | null
  grade: PanelGrade | null
  coverage: number
  uniqueProblems: number
  successWeight: number
  exposureWeight: number
  validContests: number
  rawMastery?: number | null
  rankScore?: number | null
  effectiveProblems?: number
  confidence?: number
  evidenceLevel?: 'missing' | 'exploratory' | 'provisional' | 'established' | 'legacy'
  rankEligible?: boolean
  /** Weighted expected solve rate for the observed problem set. */
  expectedMastery?: number | null
  /** Original sequential-IRT ability rating and diagnostic uncertainty. */
  ability?: number | null
  posteriorSd?: number | null
  /** Exact competition rank within the axis cohort, when available. */
  rank?: number | null
}

export interface PlayerSkillTier {
  taxonomyVersion: string
  scoreModel?: string
  scoreScale?: 'rating' | 'percent'
  contests: number
  coverage: number
  classifiedExposure: number
  unknownExposure: number
  uniqueProblems: number
  axes: Record<SkillAxisKey, PlayerSkillAxis>
}

export type PlayerSkillMode = Partial<Record<MedalTier | PanelScope, PlayerSkillTier>>

export interface PlayerSkillPanel {
  all: PlayerSkillMode
  official: PlayerSkillMode
}

export type PlayerSkillAxisRaw = [
  score: number | null,
  mastery: number | null,
  topPercent: number | null,
  grade: PanelGrade | null,
  coverage: number,
  uniqueProblems: number,
  successWeight: number,
  exposureWeight: number,
  validContests: number,
  rankScore?: number | null,
  rawMastery?: number | null,
  effectiveProblems?: number,
  confidence?: number,
  evidenceLevel?: 'missing' | 'exploratory' | 'provisional' | 'established' | 'legacy',
  rankEligible?: boolean,
  expectedMastery?: number | null,
  ability?: number | null,
  posteriorSd?: number | null,
  rank?: number | null,
]

export interface PlayerSkillTierRaw {
  taxonomyVersion: string
  scoreModel?: string
  scoreScale?: 'rating' | 'percent'
  contests: number
  coverage: number
  classifiedExposure: number
  unknownExposure: number
  uniqueProblems: number
  axes: PlayerSkillAxisRaw[]
}

export type PlayerSkillModeRaw = Partial<Record<MedalTier | PanelScope, PlayerSkillTierRaw>>

export interface PlayerSkillPanelRaw {
  all: PlayerSkillModeRaw
  official: PlayerSkillModeRaw
}

/** One tier's gold / silver / bronze medal counts. */
export interface MedalCounts {
  gold: number
  silver: number
  bronze: number
}

/**
 * Per-tier medal tally for a player. The exporter omits zero-medal tiers (and
 * omits the whole `medals` field for medal-less players), so every tier here is
 * `Partial` and a present tier always carries a full {gold,silver,bronze}
 * triple. Consumers must treat an absent tier as "no medals in that tier".
 */
export type PlayerMedals = Partial<Record<MedalTier, MedalCounts>>

/** Raw player detail differs only in its compact panel wire format. */
export type PlayerDetailRaw = Omit<PlayerDetail, 'panel' | 'skillPanel'> & {
  panel?: PlayerPanelRaw | PlayerPanel
  skillPanel?: PlayerSkillPanelRaw | PlayerSkillPanel
}

/** A shard file is a map of player key -> compact detail. */
export type PlayerShard = Record<string, PlayerDetailRaw>

/**
 * Coerce a possibly-undefined numeric field to a strict `number | null`, so a
 * field absent in a regenerating export does not leak `undefined` into the UI.
 */
function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

const PANEL_METRIC_ORDER: readonly PanelMetricKey[] = [
  'avgAc',
  'dirt',
  'rankPercent',
  'firstATime',
  'lastHourSolved',
]

function decodePanelTier(raw: PlayerPanelTierRaw): PlayerPanelTier {
  const [contests, rawMetrics, rawOverall] = raw
  const metrics = {} as Record<PanelMetricKey, PlayerPanelMetric>
  PANEL_METRIC_ORDER.forEach((key, index) => {
    const metric = rawMetrics[index]
    metrics[key] = metric
      ? {
          value: nullableNumber(metric[0]),
          topPercent: nullableNumber(metric[1]),
          grade: metric[2],
          validContests: metric[3],
        }
      : { value: null, topPercent: null, grade: null, validContests: 0 }
  })
  return {
    contests,
    metrics,
    overall: rawOverall
      ? {
          topPercent: rawOverall[0],
          grade: rawOverall[1],
          rank: rawOverall[2],
          total: rawOverall[3],
          validMetrics: rawOverall[4],
        }
      : null,
  }
}

function decodeSkillTier(raw: PlayerSkillTierRaw): PlayerSkillTier {
  const metrics = {} as Record<SkillAxisKey, PlayerSkillAxis>
  SKILL_AXIS_ORDER.forEach((key, index) => {
    const metric = raw.axes?.[index]
    metrics[key] = metric
      ? {
          score: nullableNumber(metric[0]),
          mastery: nullableNumber(metric[1]),
          topPercent: nullableNumber(metric[2]),
          grade: metric[3],
          coverage: typeof metric[4] === 'number' ? metric[4] : 0,
          uniqueProblems: typeof metric[5] === 'number' ? metric[5] : 0,
          successWeight: typeof metric[6] === 'number' ? metric[6] : 0,
          exposureWeight: typeof metric[7] === 'number' ? metric[7] : 0,
          validContests: typeof metric[8] === 'number' ? metric[8] : 0,
          rankScore: nullableNumber(metric[9]),
          rawMastery: nullableNumber(metric[10]),
          effectiveProblems: typeof metric[11] === 'number' ? metric[11] : (typeof metric[5] === 'number' ? metric[5] : 0),
          confidence: typeof metric[12] === 'number' ? metric[12] : 1,
          evidenceLevel: metric[13] ?? 'legacy',
          rankEligible: metric[14] !== false,
          expectedMastery: nullableNumber(metric[15]),
          ability: nullableNumber(metric[16]),
          posteriorSd: nullableNumber(metric[17]),
          rank: typeof metric[18] === 'number' ? metric[18] : null,
        }
      : {
          score: null,
          mastery: null,
          topPercent: null,
          grade: null,
          coverage: 0,
          uniqueProblems: 0,
          successWeight: 0,
          exposureWeight: 0,
          validContests: 0,
          rawMastery: null,
          rankScore: null,
          effectiveProblems: 0,
          confidence: 0,
          evidenceLevel: 'missing',
          rankEligible: false,
          expectedMastery: null,
          ability: null,
          posteriorSd: null,
          rank: null,
        }
  })
  return {
    taxonomyVersion: raw.taxonomyVersion,
    scoreModel: raw.scoreModel,
    scoreScale: raw.scoreScale,
    contests: raw.contests,
    coverage: raw.coverage,
    classifiedExposure: raw.classifiedExposure,
    unknownExposure: raw.unknownExposure,
    uniqueProblems: raw.uniqueProblems,
    axes: metrics,
  }
}

/** Expand a compact player-shard panel, while accepting a verbose dev fixture. */
export function decodePlayerPanel(
  raw: PlayerPanelRaw | PlayerPanel | undefined,
): PlayerPanel | undefined {
  if (!raw) return undefined
  const result: PlayerPanel = { all: {}, official: {} }
  for (const mode of ['all', 'official'] as const) {
    for (const tier of ['overall', ...MEDAL_TIER_ORDER] as const) {
      const value = raw[mode]?.[tier]
      if (!value) continue
      result[mode][tier] = Array.isArray(value)
        ? decodePanelTier(value as PlayerPanelTierRaw)
        : (value as PlayerPanelTier)
    }
    // Legacy bundles only contain tiered panels. Keep the page usable until
    // the next export writes a true cross-tier overall aggregate.
    if (!result[mode].overall) {
      const fallback = result[mode].regional ?? result[mode].final ?? result[mode].invitational ?? result[mode].provincial
      if (fallback) result[mode].overall = fallback
    }
  }
  return result
}

/** Expand a compact problem-type skill panel, tolerating legacy absence. */
export function decodePlayerSkillPanel(
  raw: PlayerSkillPanelRaw | PlayerSkillPanel | undefined,
): PlayerSkillPanel | undefined {
  if (!raw) return undefined
  const result: PlayerSkillPanel = { all: {}, official: {} }
  for (const mode of ['all', 'official'] as const) {
    for (const tier of ['overall', ...MEDAL_TIER_ORDER] as const) {
      const value = raw[mode]?.[tier]
      if (!value) continue
      result[mode][tier] = Array.isArray((value as PlayerSkillTierRaw).axes)
        ? decodeSkillTier(value as PlayerSkillTierRaw)
        : (value as PlayerSkillTier)
    }
    if (!result[mode].overall) {
      const fallback = result[mode].regional ?? result[mode].final ?? result[mode].invitational ?? result[mode].provincial
      if (fallback) result[mode].overall = fallback
    }
  }
  return result
}

/** Normalize a raw shard player so every nullable field is present as number|null. */
function normalizePlayerDetail(raw: PlayerDetailRaw): PlayerDetail {
  return {
    ...raw,
    rating: nullableNumber(raw.rating),
    allRank: nullableNumber(raw.allRank),
    officialRank: nullableNumber(raw.officialRank),
    officialRating: nullableNumber(raw.officialRating),
    skillPanel: decodePlayerSkillPanel(raw.skillPanel),
    history: raw.history.map((h) => ({
      ...h,
      official: h.official ?? true,
      rated: h.rated ?? true,
      ratedOfficial: h.ratedOfficial ?? false,
      rating_after: nullableNumber(h.rating_after),
      mu_after: nullableNumber(h.mu_after),
      perfOfficial: nullableNumber(h.perfOfficial),
      ratingAfterOfficial: nullableNumber(h.ratingAfterOfficial),
      muAfterOfficial: nullableNumber(h.muAfterOfficial),
      rankOfficial: nullableNumber(h.rankOfficial),
      teamCountOfficial: nullableNumber(h.teamCountOfficial),
    })),
  }
}

/**
 * Normalize a raw contest team so the additive fields (`preRating`, `muDelta`)
 * are always present as `number | null`. A regenerating export may omit them
 * entirely — coalesce the absent slots to null instead of letting `undefined`
 * leak into the UI. All pre-existing fields pass through untouched.
 */
function normalizeContestTeam(raw: ContestTeam): ContestTeam {
  return {
    ...raw,
    preRating: nullableNumber(raw.preRating),
    muDelta: nullableNumber(raw.muDelta),
    predictedRankOfficial: nullableNumber(raw.predictedRankOfficial),
    perfOfficial: nullableNumber(raw.perfOfficial),
    preRatingOfficial: nullableNumber(raw.preRatingOfficial),
    muDeltaOfficial: nullableNumber(raw.muDeltaOfficial),
    rankOfficial: nullableNumber(raw.rankOfficial),
    knownMembersOfficial: nullableNumber(raw.knownMembersOfficial),
  }
}

/** Normalize every team in a freshly fetched contest detail. */
function normalizeContestDetail(raw: ContestDetail): ContestDetail {
  return {
    ...raw,
    teams: raw.teams.map(normalizeContestTeam),
    problems: Array.isArray(raw.problems) ? raw.problems : undefined,
  }
}

/* ------------------------------------------------------------------ *
 * leaderboards/<kind>/{meta,pages,schools}
 * ------------------------------------------------------------------ */

export interface LeaderboardRow {
  key: string
  name: string
  org: string
  rating: number
  contests: number
  /** Full-board 1224 rank, precomputed by the exporter. */
  rank: number
}

/** Array-compressed row: `[key, name, org, rating, contests, globalRank]`. */
export type LeaderboardRowRaw = [
  key: string,
  name: string,
  org: string,
  rating: number,
  contests: number,
  rank: number,
]

function decodeLeaderboardRow(row: LeaderboardRowRaw): LeaderboardRow {
  const [key, name, org, rating, contests, rank] = row
  return { key, name, org, rating, contests, rank }
}

export type LeaderboardSchoolRaw = [org: string, count: number]

export interface LeaderboardMeta {
  total: number
  pageSize: number
  pageCount: number
  schools: LeaderboardSchoolRaw[]
}

/* ------------------------------------------------------------------ *
 * schools.json
 * ------------------------------------------------------------------ */

/**
 * One school's standing on the 学校榜, ordered by `rating` descending. `rating`
 * is the conservative TrueSkill-family estimate (μ − kσ) from the school rating
 * engine; `contests` is how many contests the school officially competed in.
 */
export interface SchoolRow {
  org: string
  rating: number
  contests: number
}

/**
 * One contest in a school's 学校成绩 history (newest first). `teamRank` is the
 * school's best official team's placement among all teams; `schoolRank` is the
 * school's standing among the contest's schools; `perf` is the performance that
 * drove the school's rating that contest. From `school-history/<shard>.json`.
 */
export interface SchoolResultRow {
  slug: string
  title: string
  startAt: string
  teamRank: number
  teamCount: number
  schoolRank: number
  schoolCount: number
  perf: number
  /** Change in the school's rating (reliable level) from this contest. */
  delta: number
}

/* ------------------------------------------------------------------ *
 * period-index.json  (array-compressed official-participation timelines)
 * ------------------------------------------------------------------ */

/**
 * One player's official-participation timeline, array-compressed:
 * `[key, name, org, dates, ratings]`. `dates` are `YYYYMMDD` ints in ascending
 * (chronological) order; `ratings` is the parallel array of official-board
 * display ratings *after* each of those contests (one decimal). Players with no
 * official participation are absent from the file entirely. Drives the 时间段
 * (period) board — see `pages/leaderboard/period.ts`.
 */
export type PeriodRow = [
  key: string,
  name: string,
  org: string,
  dates: number[],
  ratings: number[],
]

/* ------------------------------------------------------------------ *
 * Fetch layer with in-memory caching
 * ------------------------------------------------------------------ */

/** Base path for all data assets, honoring vite `base`. */
export function dataUrl(path: string): string {
  const base = import.meta.env.BASE_URL || './'
  const trimmed = base.endsWith('/') ? base : `${base}/`
  return new URL(`${trimmed}data/${path}`, document.baseURI).href
}

/**
 * Promise-level cache: storing the Promise (not the resolved value) collapses
 * concurrent requests for the same resource into a single network fetch.
 */
const cache = new Map<string, Promise<unknown>>()
const MAX_CACHED_PLAYER_SHARDS = 8

function isPlayerShardPath(path: string): boolean {
  return path.startsWith('players/') && path.endsWith('.json')
}

function trimPlayerShardCache(): void {
  let playerShardCount = 0
  for (const key of cache.keys()) {
    if (isPlayerShardPath(key)) playerShardCount += 1
  }
  while (playerShardCount > MAX_CACHED_PLAYER_SHARDS) {
    const oldest = Array.from(cache.keys()).find(isPlayerShardPath)
    if (!oldest) return
    cache.delete(oldest)
    playerShardCount -= 1
  }
}

class DataError extends Error {
  readonly path: string
  readonly status?: number

  constructor(message: string, path: string, status?: number) {
    super(message)
    this.name = 'DataError'
    this.path = path
    this.status = status
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  const cached = cache.get(path)
  if (cached) return cached as Promise<T>

  const promise = (async () => {
    let response: Response
    try {
      response = await fetch(dataUrl(path))
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : '网络请求失败'
      throw new DataError(`数据加载失败：${message}`, path)
    }

    if (!response.ok) {
      throw new DataError(
        `数据加载失败（HTTP ${response.status}）`,
        path,
        response.status,
      )
    }

    try {
      return (await response.json()) as T
    } catch {
      throw new DataError('数据解析失败：响应不是合法 JSON', path)
    }
  })()

  // Cache the in-flight promise; evict on failure so retries can re-fetch.
  cache.set(path, promise)
  // Player shards are large and user navigation can touch many of them. Keep
  // only a small hot set so a long browsing session does not retain hundreds
  // of megabytes of parsed JSON.
  if (isPlayerShardPath(path)) trimPlayerShardCache()
  promise.catch(() => {
    if (cache.get(path) === promise) cache.delete(path)
  })
  return promise
}

/** Reset the cache (test/debug aid). */
export function clearDataCache(): void {
  cache.clear()
}

export { DataError }

/* ------------------------------------------------------------------ *
 * Public API
 * ------------------------------------------------------------------ */

export function getMeta(): Promise<Meta> {
  return fetchJson<Meta>('meta.json')
}

export function getContestsIndex(): Promise<ContestIndexEntry[]> {
  return fetchJson<ContestIndexEntry[]>('contests-index.json')
}

/** A searchable row from the flat problem explorer index. */
export interface ProblemIndexRow {
  contestSlug: string
  contestTitle: string
  startAt: string
  category: string
  tier: MedalTier
  alias: string
  title: string | null
  canonicalId: string | null
  /** Public statement or contest URL for the problem, when available. */
  problemUrl?: string | null
  typeKeys: SkillAxisKey[]
  typeLabels: string[]
  /** Canonical fine-grained algorithm labels; one name per knowledge point. */
  detailTags?: string[]
  status: ContestProblemStatus
  confidence: number
  solveRate: number | null
  problemRating: number | null
  accepted: number | null
  submitted: number | null
  eligibleTeams: number
}

/**
 * Path fragments that can never be part of one problem's statement URL.
 * Mirrors `_BAD_URL_PARTS` in `scripts/merge_problem_audit.py`.
 */
const BAD_URL_PARTS = ['/rank', '/standings', '/ranking', '/download', '/tutorial', '/attachment', '.pdf'] as const

/**
 * Whether a URL points at one problem rather than a contest/rank/tutorial page.
 *
 * Faithful port of `individual_url()` in `scripts/merge_problem_audit.py`, the
 * classifier the audit pipeline uses to decide whether a candidate link is a
 * real single-problem statement, so the problem bank lists exactly the rows the
 * audit accepts as directly openable.
 */
export function isIndividualProblemUrl(value: string | null | undefined): boolean {
  const text = value?.trim()
  if (!text) return false
  let url: URL
  try {
    url = new URL(text)
  } catch {
    return false
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return false
  if (!url.hostname) return false
  let path: string
  try {
    path = decodeURIComponent(url.pathname).replace(/\/+$/, '').toLowerCase()
  } catch {
    path = url.pathname.replace(/\/+$/, '').toLowerCase()
  }
  if (BAD_URL_PARTS.some((token) => path.includes(token))) return false
  const parts = path.split('/').filter(Boolean)
  const host = url.hostname.toLowerCase()

  if (host.endsWith('codeforces.com')) {
    return (
      /\/gym\/\d+\/problem\/[a-z0-9][a-z0-9_-]*$/.test(path) ||
      /\/contest\/\d+\/problem\/[a-z0-9][a-z0-9_-]*$/.test(path)
    )
  }
  if (host.endsWith('qoj.ac') || host.endsWith('ucup.ac') || host.endsWith('jiang.ly')) {
    return /\/problem\/\d+$/.test(path) || /\/contest\/\d+\/problem\/\d+$/.test(path)
  }
  if (host.endsWith('nowcoder.com')) {
    return (
      /\/acm\/contest\/\d+\/[a-z0-9][a-z0-9_-]*$/.test(path) ||
      /\/acm\/problem\/[a-z0-9][a-z0-9_-]*$/.test(path)
    )
  }
  if (host.endsWith('luogu.com.cn')) return /\/problem\/p\d+$/.test(path)
  if (host.endsWith('vjudge.net')) return path.includes('/problem/') || path.includes('/problemset/')
  if (host.endsWith('pintia.cn')) return path.includes('/problem-sets/') && path.includes('/problems/')
  // Atuer/Hydro exposes one problem as `/p/<problem-id>`.
  if (host.endsWith('atuer.cn')) return /^\/p\/[a-z0-9][a-z0-9_-]*$/.test(path)
  if (parts.includes('problem') && parts.length >= 2) return true
  // Some official mirrors only put the alias last, behind a problem-ish noun.
  const parent = parts.length >= 2 ? parts[parts.length - 2] : ''
  return /problem|question|task/.test(parent)
}

/**
 * Whether a title really names the problem.
 *
 * Placeholder titles ("未命名题目", the bare alias) and decoding failures stay
 * out of the problem bank: a row without a name, a type or a rating is an
 * unresolved audit row, not a browsable problem (its contest page still lists
 * it).
 */
export function validProblemTitle(
  value: string | null | undefined,
  alias?: string | null,
): boolean {
  const text = value?.trim() ?? ''
  if (!text || text === alias || text === '未命名题目') return false
  return !text.includes('\uFFFD')
}

/** Load the flat problem index used by the problem browser filters.
 *
 * The problem bank only lists problems whose link actually opens that one
 * statement and whose title really names it. Rows with no URL, a
 * contest/rank/tutorial URL, or an unresolved title are not offered here (the
 * contest pages still show them).
 */
export function getProblemsIndex(): Promise<ProblemIndexRow[]> {
  return fetchJson<ProblemIndexRow[]>('problems-index.json').then((rows) =>
    rows.filter((row) => isIndividualProblemUrl(row.problemUrl) && validProblemTitle(row.title, row.alias)),
  )
}

export function getPredictionsIndex(): Promise<PredictionIndexEntry[]> {
  return fetchJson<PredictionIndexEntry[]>('predictions-index.json')
}

export function getPrediction(slug: string): Promise<PredictionDetail> {
  return fetchJson<PredictionDetail>(`predictions/${slug}.json`)
}

export async function getContest(slug: string): Promise<ContestDetail> {
  const raw = await fetchJson<ContestDetail>(`contests/${slug}.json`)
  return normalizeContestDetail(raw)
}

function leaderboardRoot(official: boolean): string {
  return `leaderboards/${official ? 'official' : 'all'}`
}

export function getLeaderboardMeta(official = false): Promise<LeaderboardMeta> {
  return fetchJson<LeaderboardMeta>(`${leaderboardRoot(official)}/meta.json`)
}

/** Load exactly one 100-row leaderboard page. */
export async function getLeaderboardPage(
  official: boolean,
  page: number,
): Promise<LeaderboardRow[]> {
  const rows = await fetchJson<LeaderboardRowRaw[]>(
    `${leaderboardRoot(official)}/pages/${page}.json`,
  )
  return rows.map(decodeLeaderboardRow)
}

/** Load one school's complete board slice; rows retain their global ranks. */
export async function getLeaderboardSchool(
  official: boolean,
  org: string,
): Promise<LeaderboardRow[]> {
  const bucket = await fetchJson<Record<string, LeaderboardRowRaw[]>>(
    `${leaderboardRoot(official)}/schools/${shardForKey(org)}.json`,
  )
  return (bucket[org] ?? []).map(decodeLeaderboardRow)
}

/** Load the candidate shard selected by the query, with a pinyin fallback. */
export async function getPlayerSearchPrefix(
  query: string,
): Promise<PlayerSearchEntry[]> {
  const shard = playerSearchShard(query)
  if (!shard) return []
  try {
    const rows = await fetchJson<PlayerSearchRow[]>(
      `search/players/${shard}.json`,
    )
    const direct = decodePlayerSearchRows(rows)
    if (!looksLikePinyinQuery(query) || query.trim().length > 6 || filterPlayerSearchEntries(direct, query).length > 0) {
      return direct
    }

    // Pinyin initials do not share the original Chinese first-character shard.
    // Only pay the broader lookup cost after a short, letter-only query misses.
    const shards = Array.from({ length: 256 }, (_, index) => index.toString(16).padStart(2, '0'))
    const results = await Promise.allSettled(
      shards.map((candidate) => fetchJson<PlayerSearchRow[]>(`search/players/${candidate}.json`)),
    )
    const seen = new Set<string>()
    const merged: PlayerSearchEntry[] = []
    for (const result of results) {
      if (result.status !== 'fulfilled') continue
      for (const entry of decodePlayerSearchRows(result.value)) {
        if (seen.has(entry.key)) continue
        seen.add(entry.key)
        merged.push(entry)
      }
    }
    return merged
  } catch (error: unknown) {
    if (error instanceof DataError && error.status === 404) return []
    throw error
  }
}

/** The 学校榜 (school ranking), ordered by conservative rating descending. */
export function getSchools(): Promise<SchoolRow[]> {
  return fetchJson<SchoolRow[]>('schools.json')
}

/**
 * A school's per-contest results (学校成绩), newest first. Derives the md5 shard
 * from the org, loads it once (cached), then indexes by org; an org with no
 * history (or absent shard) yields an empty list.
 */
export async function getSchoolHistory(org: string): Promise<SchoolResultRow[]> {
  const shard = shardForKey(org)
  const data = await fetchJson<Record<string, SchoolResultRow[]>>(
    `school-history/${shard}.json`,
  )
  return data[org] ?? []
}

/**
 * Resolve a single player by key. Internally derives the md5 shard (first two
 * hex chars), loads that shard once (cached), then indexes into it. Throws a
 * DataError if the key is absent from its shard.
 */
export async function getPlayer(key: string): Promise<PlayerDetail> {
  const shard = shardForKey(key)
  const data = await fetchJson<PlayerShard>(`players/${shard}.json`)
  const detail = data[key]
  if (!detail) {
    throw new DataError(`未找到选手：${key}`, `players/${shard}.json`)
  }
  return normalizePlayerDetail(detail)
}

/** Minimal player row used by the on-demand problem-type leaderboard. */
export interface SkillLeaderboardPlayerData {
  key: string
  name: string
  org: string
  skillPanel?: PlayerSkillPanel
}

/** One precomputed row from a single problem-type leaderboard. */
export interface SkillLeaderboardIndexRow {
  key: string
  name: string
  org: string
  score: number
  topPercent: number | null
  grade: PanelGrade | null
  uniqueProblems: number
  coverage: number
  rankScore?: number
  effectiveProblems?: number
  evidenceLevel?: string
  confidence?: number
}

export interface SkillLeaderboardIndex {
  version: string
  mode: 'all' | 'official'
  tier: MedalTier | PanelScope
  axis: SkillAxisKey
  rows: SkillLeaderboardIndexRow[]
}

/**
 * Expand the compact axis board written by the exporter.
 *
 * The implementation lives in ``skillLeaderboardCodec`` so the skill-board Web
 * Worker can decode rows without importing this whole module; re-exported here
 * for the main-thread fallback and for the tests.
 */
export { decodeSkillLeaderboardRows } from './skillLeaderboardCodec'

/** Load one precomputed axis board; unlike the legacy fallback this is one small request. */
export function getSkillLeaderboardIndex(
  mode: 'all' | 'official',
  tier: MedalTier | PanelScope,
  axis: SkillAxisKey,
): Promise<SkillLeaderboardIndex> {
  return fetchJson<SkillLeaderboardIndex & { rowFields?: unknown }>(
    `skill-leaderboards/${mode}/${tier}/${axis}.json`,
  )
    .then(decodeSkillLeaderboardRows)
    .catch((error) => {
      if (tier !== 'overall') throw error
      return fetchJson<SkillLeaderboardIndex & { rowFields?: unknown }>(
        `skill-leaderboards/${mode}/regional/${axis}.json`,
      ).then(decodeSkillLeaderboardRows)
    })
}

/**
 * Load the skill-bearing player shards for the optional global leaderboard.
 *
 * The current static contract has no separate skill index, so this is an
 * explicit on-demand fallback. Missing legacy shards are ignored; callers can
 * present an unavailable state when no shard contains a skill panel.
 */
export async function getSkillLeaderboardPlayers(): Promise<SkillLeaderboardPlayerData[]> {
  const shards = Array.from({ length: 256 }, (_, index) =>
    index.toString(16).padStart(2, '0'),
  )
  const results = await Promise.allSettled(
    shards.map((shard) => fetchJson<PlayerShard>(`players/${shard}.json`)),
  )
  const players: SkillLeaderboardPlayerData[] = []
  for (const result of results) {
    if (result.status !== 'fulfilled') continue
    for (const [key, raw] of Object.entries(result.value)) {
      const skillPanel = decodePlayerSkillPanel(raw.skillPanel)
      if (!skillPanel) continue
      players.push({ key, name: raw.name, org: raw.org, skillPanel })
    }
  }
  return players
}
