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

/**
 * 这个词应该竖排吗。
 *
 * 只有**短的纯拉丁/数字标签**才竖排（DP / KMP / NTT 这类）。两个理由：
 *   * 多向排版会明显伤害词云的可读性（Displays 2024 有专门研究）；
 *   * 中文方块字转 90° 之后比拉丁字母难认得多——拉丁字母有上升部/下降部，
 *     转过去还能靠轮廓辨识，汉字转过去就是一列方块。
 *
 * 用标签自身的哈希决定而不是随机数：必须保证同一个标签每次渲染结果一致，
 * 否则每次重排词都会跳。
 */
const ROTATABLE = /^[A-Za-z0-9+]{2,4}$/

export function wordCloudRotate(text: string): number {
  if (!ROTATABLE.test(text)) return 0
  let hash = 0
  for (const char of Array.from(text)) {
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

/** 词云占画布的比例：留一点边距，别让词贴着边缘。 */
const FILL = 0.92
/** 相邻两圈之间的径向步长（像素，按画布最长半轴折算）。 */
const RADIAL_STEP = 2
/** 同一圈上相邻采样点之间的弧长（像素）。 */
const ARC_STEP = 4

/**
 * 从中心往外螺旋找一个放得下的位置。
 *
 * **按椭圆采样，不是圆。** 纯圆螺线在宽画布上会先撞到上下边界，于是左右大片留白
 * ——实测 1022px 宽的画布上词云只占了 651px。把归一化的半径映射到画布的两个半轴上，
 * 词云就会贴合容器比例铺开。
 *
 * 环上的采样点按弧长均匀分布（半径越大采样越密），这样不会出现"某些角度永远试不到"的缝。
 */
function findSlot(
  width: number,
  height: number,
  placed: readonly PlacedWord[],
  spec: WordCloudSpec,
): { x: number; y: number } | null {
  // 留一点边距，别让词贴着画布边缘
  const halfWidth = (spec.width / 2) * FILL
  const halfHeight = (spec.height / 2) * FILL
  const longest = Math.max(halfWidth, halfHeight)
  const tStep = Math.max(RADIAL_STEP / longest, 0.004)

  for (let t = tStep; t <= 1.0001; t += tStep) {
    const ringX = t * halfWidth
    const ringY = t * halfHeight
    const samples = Math.max(8, Math.ceil((2 * Math.PI * Math.max(ringX, ringY)) / ARC_STEP))
    for (let index = 0; index < samples; index += 1) {
      const angle = (index / samples) * 2 * Math.PI
      // 先取整再判定：坐标必须是整数，否则"确定性"会因为浮点尾数而不成立
      const x = Math.round(Math.cos(angle) * ringX)
      const y = Math.round(Math.sin(angle) * ringY)
      if (Math.abs(x) + width / 2 > spec.width / 2) continue
      if (Math.abs(y) + height / 2 > spec.height / 2) continue
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
 * 字号自适应：让词云把画布铺满，而不是缩成中间一小团。
 *
 * 词云是从中心紧密堆出来的，画布边界只是**上限**不是目标 —— 43 个标签排完后实测只占了
 * 1022px 画布里的 548px，两侧空得明显。所以排完一遍之后量一下包围盒，按比例缩放字号
 * 再排，迭代几次贴到目标宽度。
 *
 * 包围盒的宽度近似与字号线性相关（字号乘 k，总面积乘 k²，半径乘 k），所以缩放比直接
 * 用目标宽/当前宽即可，不需要二分。
 */
export interface FitOptions {
  /** 目标：词云至少占到画布宽度的这个比例。 */
  minWidthRatio?: number
  /** 上限：超过就会被裁掉。 */
  maxWidthRatio?: number
  maxHeightRatio?: number
  /** 字号最多放大到几倍。 */
  maxScale?: number
  iterations?: number
}

function withScale(
  items: readonly ScaledAlgorithmTag[],
  scale: number,
): ScaledAlgorithmTag[] {
  return items.map((item) => ({
    ...item,
    fontSize: Math.max(1, Math.round(item.fontSize * scale)),
  }))
}

export function fitWordCloud(
  items: readonly ScaledAlgorithmTag[],
  spec: WordCloudSpec,
  options: FitOptions = {},
): WordCloudLayout {
  const minWidthRatio = options.minWidthRatio ?? 0.86
  const maxWidthRatio = options.maxWidthRatio ?? 0.97
  const maxHeightRatio = options.maxHeightRatio ?? 0.97
  const maxScale = options.maxScale ?? 2.4
  const iterations = options.iterations ?? 4

  const maxWidth = spec.width * maxWidthRatio
  const maxHeight = spec.height * maxHeightRatio
  const minWidth = spec.width * minWidthRatio

  let scale = 1
  let layout = layoutWordCloud(items, spec)

  for (let attempt = 0; attempt < iterations; attempt += 1) {
    const drawnWidth = layout.bounds.maxX - layout.bounds.minX
    const drawnHeight = layout.bounds.maxY - layout.bounds.minY
    const overflows = drawnWidth > maxWidth || drawnHeight > maxHeight
    const tooSmall = drawnWidth < minWidth && scale < maxScale

    if (!overflows && !tooSmall) break

    // 包围盒近似与字号成正比，所以直接按比例调；overflow 时留 4% 余量避免来回震荡
    const room = Math.min(maxWidth / Math.max(drawnWidth, 1), maxHeight / Math.max(drawnHeight, 1))
    const next = overflows ? scale * room * 0.96 : Math.min(scale * room, maxScale)
    if (Math.abs(next - scale) < 0.02) break
    scale = next
    layout = layoutWordCloud(withScale(items, scale), spec)
  }

  return layout
}

/**
 * 把带权重的标签排成一张互不重叠的词云。
 *
 * 放不下的词会被丢掉而不是硬塞——所以调用方要接受 `words.length < items.length`，
 * 并按 `bounds` 裁剪画布，不要假定所有标签都排上了。
 *
 * 想要"铺满画布"的效果请用 `fitWordCloud`，它在外面套了一层字号自适应。
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
