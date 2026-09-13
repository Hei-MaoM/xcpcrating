const INITIALS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'w', 'x', 'y', 'z'] as const

// The old GB2312 boundary table cannot be compared with JavaScript Unicode
// code points. These representatives are ordered by their Mandarin pinyin;
// the locale collation gives us the initial without bundling a 20k-character
// dictionary into the search UI.
const INITIAL_REPRESENTATIVES = ['阿', '波', '擦', '搭', '鹅', '发', '嘎', '哈', '击', '喀', '垃', '妈', '拿', '哦', '啪', '期', '然', '撒', '塌', '挖', '昔', '压', '杂'] as const
const PINYIN_COLLATOR = new Intl.Collator('zh-Hans-u-co-pinyin', { sensitivity: 'base' })

function chineseInitial(char: string): string | null {
  const codePoint = char.charCodeAt(0)
  if (codePoint < 0x4e00 || codePoint > 0x9fff) return null
  let index = 0
  for (let i = 1; i < INITIAL_REPRESENTATIVES.length; i += 1) {
    if (PINYIN_COLLATOR.compare(char, INITIAL_REPRESENTATIVES[i]) >= 0) {
      index = i
    } else {
      break
    }
  }
  return INITIALS[index] ?? null
}

/** Return compact initials for Chinese text while preserving Latin letters. */
export function pinyinInitials(value: string): string {
  return Array.from(value.trim().toLowerCase())
    .map((char) => chineseInitial(char) ?? (/^[a-z0-9]$/.test(char) ? char : ''))
    .join('')
}

export function looksLikePinyinQuery(value: string): boolean {
  return /^[a-z]{2,}$/.test(value.trim().toLowerCase())
}
