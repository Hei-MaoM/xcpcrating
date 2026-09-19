const INITIALS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'w', 'x', 'y', 'z'] as const

// The old GB2312 boundary table cannot be compared with JavaScript Unicode
// code points. These representatives are ordered by their Mandarin pinyin;
// the locale collation gives us the initial without bundling a 20k-character
// dictionary into the search UI.
const INITIAL_REPRESENTATIVES = ['阿', '波', '擦', '搭', '鹅', '发', '嘎', '哈', '击', '喀', '垃', '妈', '拿', '哦', '啪', '期', '然', '撒', '塌', '挖', '昔', '压', '杂'] as const
const PINYIN_COLLATOR = new Intl.Collator('zh-Hans-u-co-pinyin', { sensitivity: 'base' })

/**
 * 单个汉字的声母，按字符记忆化。
 *
 * 原来是每个字符现算一遍：对 23 个代表字做 `Intl.Collator.compare` 的二分查找。
 * 而搜索要对 13.7 万行 ×（姓名 + 学校）调 `pinyinInitials`，也就是**每次查询
 * 几千万次 collator 调用，而且全在主线程上** —— 输入一个字母卡好几秒就是这么来的。
 *
 * 汉字是有限的（常用字几千个），按字符缓存之后每个字只算一次，之后都是 Map 命中。
 * 空串是"这个字符没有声母"的哨兵，所以要区分"没缓存过"和"缓存了空值"。
 */
const INITIAL_CACHE = new Map<string, string>()

function chineseInitial(char: string): string | null {
  const cached = INITIAL_CACHE.get(char)
  if (cached !== undefined) return cached || null

  const codePoint = char.charCodeAt(0)
  if (codePoint < 0x4e00 || codePoint > 0x9fff) {
    INITIAL_CACHE.set(char, '')
    return null
  }
  let index = 0
  for (let i = 1; i < INITIAL_REPRESENTATIVES.length; i += 1) {
    if (PINYIN_COLLATOR.compare(char, INITIAL_REPRESENTATIVES[i]) >= 0) {
      index = i
    } else {
      break
    }
  }
  const initial = INITIALS[index] ?? ''
  INITIAL_CACHE.set(char, initial)
  return initial || null
}

/**
 * 整个字符串的声母串，也记忆化。
 *
 * 名字基本不重复，但**学校名高度重复**（13.7 万行只对应几千所学校），
 * 所以这一层能省掉大量重复计算。上限只是防止无限增长，实际数据量远达不到。
 */
const TEXT_CACHE = new Map<string, string>()
const TEXT_CACHE_LIMIT = 300_000

/** Return compact initials for Chinese text while preserving Latin letters. */
export function pinyinInitials(value: string): string {
  const normalized = value.trim().toLowerCase()
  const cached = TEXT_CACHE.get(normalized)
  if (cached !== undefined) return cached

  const result = Array.from(normalized)
    .map((char) => chineseInitial(char) ?? (/^[a-z0-9]$/.test(char) ? char : ''))
    .join('')
  if (TEXT_CACHE.size < TEXT_CACHE_LIMIT) TEXT_CACHE.set(normalized, result)
  return result
}

export function looksLikePinyinQuery(value: string): boolean {
  return /^[a-z]{2,}$/.test(value.trim().toLowerCase())
}
