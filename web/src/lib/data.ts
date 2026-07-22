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
import {
  decodePlayerSearchRows,
  playerSearchShard,
  type PlayerSearchEntry,
  type PlayerSearchRow,
} from './search'

/* ------------------------------------------------------------------ *
 * meta.json
 * ------------------------------------------------------------------ */

export interface MetaCounts {
  contests: number
  players: number
  ratedPlayers: number
  predictions?: number
}

export interface Meta {
  generatedAt: string
  /** Provenance only ("incremental"); never shown in the UI. */
  engine: string
  counts: MetaCounts
}

/* ------------------------------------------------------------------ *
 * contests-index.json
 * ------------------------------------------------------------------ */

export interface Champion {
  name: string
  org: string
}

export interface ContestIndexEntry {
  id: string
  slug: string
  title: string
  startAt: string
  category: string
  teamCount: number
  champion: Champion
  /** Voided contest (e.g. leaked problems): displayed but scored unrated. */
  unrated?: boolean
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
}

export interface ContestDetail {
  id: string
  slug: string
  title: string
  startAt: string
  category: string
  teamCount: number
  /** Pre-contest prediction hit-rate for this contest; null when undefined. */
  concordance: number | null
  /** Voided contest (e.g. leaked problems): displayed but scored unrated. */
  unrated?: boolean
  /** Reason shown on the contest page when unrated. */
  unratedNote?: string | null
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
  startAt: string
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

/** Display order for medal tiers (most prestigious first). */
export const MEDAL_TIER_ORDER: readonly MedalTier[] = [
  'final',
  'regional',
  'invitational',
  'provincial',
]

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

/** A shard file is a map of player key -> detail. */
export type PlayerShard = Record<string, PlayerDetail>

/**
 * Coerce a possibly-undefined numeric field to a strict `number | null`, so a
 * field absent in a regenerating export does not leak `undefined` into the UI.
 */
function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

/** Normalize a raw shard player so every nullable field is present as number|null. */
function normalizePlayerDetail(raw: PlayerDetail): PlayerDetail {
  return {
    ...raw,
    rating: nullableNumber(raw.rating),
    allRank: nullableNumber(raw.allRank),
    officialRank: nullableNumber(raw.officialRank),
    officialRating: nullableNumber(raw.officialRating),
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
  }
}

/** Normalize every team in a freshly fetched contest detail. */
function normalizeContestDetail(raw: ContestDetail): ContestDetail {
  return {
    ...raw,
    teams: raw.teams.map(normalizeContestTeam),
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
  promise.catch(() => cache.delete(path))
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

/** Load only the player candidate shard selected by the query's first char. */
export async function getPlayerSearchPrefix(
  query: string,
): Promise<PlayerSearchEntry[]> {
  const shard = playerSearchShard(query)
  if (!shard) return []
  try {
    const rows = await fetchJson<PlayerSearchRow[]>(
      `search/players/${shard}.json`,
    )
    return decodePlayerSearchRows(rows)
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
