import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ProblemIndexRow } from '../../lib/data'
import { countAlgorithmTags, scaleTagWeights } from './settersPresentation'
import { fitWordCloud, type WordCloudSpec } from './settersWordCloudLayout'

/**
 * 算法词云。
 *
 * 排版交给 `settersWordCloudLayout`（阿基米德螺线、最重的先放、互相不重叠），
 * 这里只负责三件事：量出容器宽度、用真实字体量文字尺寸、把结果绝对定位画出来。
 *
 * 设计取舍：
 *   * **几乎不旋转**。多向排版会显著伤害词云的可读性，而中文方块字转 90° 之后
 *     比拉丁字母难认得多，所以只有 ≤4 字符的纯拉丁标签（DP / KMP / NTT）才竖排。
 *   * **不用随机颜色**。随机色会暗示不存在的含义；沿用 hot / mid / cool 三档，
 *     映射到站点既有的 oxford 色系。
 *   * **放不下就丢**，并把"N / M 个标签"如实写出来，而不是硬塞到重叠。
 */

/** 与 `--serif` 保持一致；运行时读不到 CSS 变量时退回这份字面量。 */
const SERIF_FALLBACK = '"SimSun", "Songti SC", STSong, "Noto Serif CJK SC", ui-serif, serif'

/** 画布上下各留一点，免得最上/最下的词贴边或被裁掉。 */
const PAD_Y = 4

/** 宽画布用扁平比例；窄屏允许更高，否则大半标签会因为放不下被丢掉。 */
function aspectFor(width: number): number {
  if (width >= 720) return 0.42
  if (width >= 520) return 0.55
  return 0.85
}

/** 字号也随宽度收：手机上 38px 的标签一个就占掉半屏。 */
function sizeRangeFor(width: number): { minSize: number; maxSize: number } {
  if (width >= 720) return { minSize: 13, maxSize: 38 }
  if (width >= 520) return { minSize: 12, maxSize: 30 }
  return { minSize: 11, maxSize: 23 }
}

/**
 * 用离屏 canvas 量文字尺寸。
 *
 * 必须用**真实的字体栈**去量：中文是等宽方块，但拉丁标签（DP / KMP / NTT）宽度差很多，
 * 衬线体和雅黑也不一样。量不准就会出现重叠或大片空隙。
 * 行高取 1.2 与 CSS 一致，否则纵向的碰撞判定会比实际渲染的高。
 */
function createMeasurer(getWeight: (text: string) => number) {
  const context = document.createElement('canvas').getContext('2d')
  const serif =
    typeof window === 'undefined'
      ? SERIF_FALLBACK
      : getComputedStyle(document.documentElement).getPropertyValue('--serif').trim() ||
        SERIF_FALLBACK

  return (text: string, fontSize: number): { width: number; height: number } => {
    const height = fontSize * 1.2
    if (!context) return { width: Array.from(text).length * fontSize, height }
    context.font = `${getWeight(text)} ${fontSize}px ${serif}`
    return { width: Math.ceil(context.measureText(text).width), height }
  }
}

/**
 * 量容器宽度。
 *
 * **必须用 callback ref，不能用 useRef + useEffect[ref]。** 数据没加载完时组件会走早返回
 * 分支，那会儿画布 div 还没挂上，`ref.current` 是 null，effect 直接 return；等数据到了
 * 画布挂上去，effect 的依赖 `[ref]` 没变所以不会重跑 —— 宽度就永远停在 0，
 * 结果是一个词都排不出来（实测就是这样，页面上显示 "0 / 79 个标签"）。
 *
 * callback ref 在元素挂载/卸载时都会触发，正好是测量的正确时机。
 */
function useContainerWidth(): { width: number; attach: (element: HTMLDivElement | null) => void } {
  const [width, setWidth] = useState(0)
  const observerRef = useRef<ResizeObserver | null>(null)

  const attach = useCallback((element: HTMLDivElement | null) => {
    observerRef.current?.disconnect()
    observerRef.current = null
    if (!element) return

    const update = () => {
      const next = Math.round(element.clientWidth)
      setWidth((current) => (current === next ? current : next))
    }
    update()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(update)
    observer.observe(element)
    observerRef.current = observer
  }, [])

  useEffect(() => () => observerRef.current?.disconnect(), [])

  return { width, attach }
}

export function SetterWordCloud({
  problems,
  slugs,
}: {
  problems: readonly ProblemIndexRow[] | null
  slugs: ReadonlySet<string> | null
}) {
  const { width, attach } = useContainerWidth()

  const items = useMemo(() => {
    if (!problems || !slugs) return null
    return scaleTagWeights(countAlgorithmTags(problems, slugs), sizeRangeFor(width || 720))
  }, [problems, slugs, width])

  const layout = useMemo(() => {
    if (!items || width <= 0) return null
    const byTag = new Map(items.map((item) => [item.tag, item]))
    const spec: WordCloudSpec = {
      width,
      height: Math.round(width * aspectFor(width)),
      padding: width >= 520 ? 4 : 3,
      measure: createMeasurer((text) => byTag.get(text)?.weight ?? 600),
    }
    const result = fitWordCloud(items, spec)
    return {
      // 排版结果只带几何信息，视觉属性在这里贴回去，避免渲染时再做一次查找
      words: result.words.map((word) => ({
        ...word,
        tone: byTag.get(word.tag)?.tone ?? 'cool',
        weight: byTag.get(word.tag)?.weight ?? 500,
        opacity: byTag.get(word.tag)?.opacity ?? 0.8,
      })),
      bounds: result.bounds,
      total: items.length,
    }
  }, [items, width])

  if (items === null) {
    return (
      <section className="setter-cloud" aria-busy="true" aria-label="算法词云">
        <p className="setter-cloud__status">正在统计算法标签…</p>
      </section>
    )
  }

  if (items.length === 0) {
    return (
      <section className="setter-cloud" aria-label="算法词云">
        <p className="setter-cloud__status">还没有可用的算法标签。</p>
      </section>
    )
  }

  const bounds = layout?.bounds
  const boxHeight = bounds ? Math.ceil(bounds.maxY - bounds.minY) + PAD_Y * 2 : 0

  return (
    <section className="setter-cloud" aria-label="算法词云">
      <div className="setter-cloud__head">
        <span className="setter-cloud__kicker">算法词云</span>
        <span className="setter-cloud__meta tnum">
          {layout && layout.words.length === layout.total
            ? `${layout.total} 个标签`
            : `${layout?.words.length ?? 0} / ${items.length} 个标签`}
        </span>
      </div>
      <div
        className="setter-cloud__canvas"
        ref={attach}
        style={{ height: boxHeight > 0 ? boxHeight : 180 }}
      >
        {bounds
          ? layout!.words.map((word) => (
              <span
                key={word.tag}
                className={`setter-cloud__word setter-cloud__word--${word.tone}`}
                style={{
                  fontSize: `${word.fontSize}px`,
                  fontWeight: word.weight,
                  opacity: word.opacity,
                  // 先按自身尺寸平移一半、再挪到排版坐标 —— 于是 (x, y) 就是这个词的中心
                  transform: `translate(-50%, -50%) translate(${word.x}px, ${
                    word.y - bounds.minY + PAD_Y
                  }px)`,
                  writingMode: word.rotate === 90 ? 'vertical-rl' : undefined,
                }}
                title={`${word.tag} · ${word.count} 题`}
                aria-label={`${word.tag}，${word.count} 题`}
              >
                {word.tag}
              </span>
            ))
          : null}
      </div>
    </section>
  )
}
