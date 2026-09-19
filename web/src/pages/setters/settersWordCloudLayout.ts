import type { ScaledAlgorithmTag } from './settersPresentation'

/**
 * 词云排版。
 *
 * 组件目前用的是 CSS 流式排版（`SetterWordCloud.tsx`），这里是把它换成"按权重居中、
 * 螺旋找位、互不重叠"的紧凑排版所需的引擎。规格由 `settersWordCloudLayout.test.ts` 定死，
 * 这里是按那份规格实现的。
 *
 * 三个必须成立的性质：
 *   * **确定性** —— 同样的输入必须给出完全相同的坐标，否则每次渲染词都会跳
 *   * **不重叠** —— 任意两个词的方框都不能相交（含 padding）
 *   * **最重的词在原点** —— 视觉重心居中，轻的往边上挤
 */

export interface WordCloudMeasure {
  (text: string, fontSize: number): { width: number; height: number }
}

export interface WordCloudSpec {
  width: number
  height: number
  padding: number
  measure: WordCloudMeasure
}

export interface PlacedWord {
  tag: string
  count: number
  fontSize: number
  /** 相对画布中心的坐标。 */
  x: number
  y: number
  width: number
  height: number
  rotate: number
}

export interface WordCloudBounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

export interface WordCloudLayout {
  words: PlacedWord[]
  bounds: WordCloudBounds
}

/** 超过这个字数就横排——竖排长标签难读，而且会浪费画布。 */
const ROTATE_MAX_LENGTH = 4

/**
 * 这个词应该竖排吗。只对短标签开放竖排，而且用标签自身的哈希决定，
 * 保证同一个标签每次渲染结果一致（不能用随机数，否则词会跳）。
 */
export function wordCloudRotate(text: string): number {
  const chars = Array.from(text)
  if (chars.length > ROTATE_MAX_LENGTH) return 0
  let hash = 0
  for (const char of chars) {
    hash = (hash * 31 + (char.codePointAt(0) ?? 0)) >>> 0
  }
  return hash % 2 === 0 ? 0 : 90
}

/** 两个方框是否相交（含 padding）。 */
function intersects(
  x: number,
  y: number,
  width: number,
  height: number,
  other: PlacedWord,
  padding: number,
): boolean {
  return (
    Math.abs(x - other.x) * 2 < width + other.width + padding * 2 &&
    Math.abs(y - other.y) * 2 < height + other.height + padding * 2
  )
}

/**
 * 从中心往外螺旋找一个放得下的位置。
 *
 * 用同心圆环而不是阿基米德螺线：环上的采样点按弧长均匀分布，半径越大采样越密，
 * 这样大画布上也不会出现"某些角度永远试不到"的缝。
 */
function findSlot(
  width: number,
  height: number,
  placed: readonly PlacedWord[],
  spec: WordCloudSpec,
): { x: number; y: number } | null {
  const halfWidth = spec.width / 2
  const halfHeight = spec.height / 2
  const radialStep = 2
  const arcStep = 4
  const maxRadius = Math.hypot(halfWidth, halfHeight) + Math.max(width, height)

  for (let radius = radialStep; radius <= maxRadius; radius += radialStep) {
    const samples = Math.max(8, Math.ceil((2 * Math.PI * radius) / arcStep))
    for (let index = 0; index < samples; index += 1) {
      const angle = (index / samples) * 2 * Math.PI
      // 先取整再判定：坐标必须是整数，否则"确定性"会因为浮点尾数而不成立
      const x = Math.round(Math.cos(angle) * radius)
      const y = Math.round(Math.sin(angle) * radius)
      if (Math.abs(x) + width / 2 > halfWidth) continue
      if (Math.abs(y) + height / 2 > halfHeight) continue
      if (placed.some((other) => intersects(x, y, width, height, other, spec.padding))) continue
      return { x, y }
    }
  }
  return null
}

function boundsOf(words: readonly PlacedWord[]): WordCloudBounds {
  if (words.length === 0) return { minX: 0, maxX: 0, minY: 0, maxY: 0 }
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const word of words) {
    minX = Math.min(minX, word.x - word.width / 2)
    maxX = Math.max(maxX, word.x + word.width / 2)
    minY = Math.min(minY, word.y - word.height / 2)
    maxY = Math.max(maxY, word.y + word.height / 2)
  }
  return { minX, maxX, minY, maxY }
}

/**
 * 把带权重的标签排成一张互不重叠的词云。
 *
 * 放不下的词会被丢掉而不是硬塞——所以调用方要接受 `words.length < items.length`，
 * 并按 `bounds` 裁剪画布，不要假定所有标签都排上了。
 */
export function layoutWordCloud(
  items: readonly ScaledAlgorithmTag[],
  spec: WordCloudSpec,
): WordCloudLayout {
  const words: PlacedWord[] = []

  // 重的先放：先占中心，轻的再往空隙里塞
  const ordered = [...items].sort((a, b) => b.count - a.count)

  for (const item of ordered) {
    const measured = spec.measure(item.tag, item.fontSize)
    const rotate = wordCloudRotate(item.tag)
    // 竖排就是把方框转 90 度
    const width = rotate === 90 ? measured.height : measured.width
    const height = rotate === 90 ? measured.width : measured.height

    // 最重的那个无条件放在原点，即使画布小到装不下它 ——
    // 这样极小画布下也至少有一个词，而不是整块空白
    const slot = words.length === 0 ? { x: 0, y: 0 } : findSlot(width, height, words, spec)
    if (!slot) continue

    words.push({
      tag: item.tag,
      count: item.count,
      fontSize: item.fontSize,
      x: slot.x,
      y: slot.y,
      width,
      height,
      rotate,
    })
  }

  return { words, bounds: boundsOf(words) }
}
