import { deviationDirection, rankGap } from '../../lib/format'

interface DeviationCellProps {
  predictedRank: number | null | undefined
  actualRank: number | null | undefined
}

const ARROW: Record<'up' | 'down' | 'flat', string> = {
  up: '▲',
  down: '▼',
  flat: '–',
}

const LABEL: Record<'up' | 'down' | 'flat', string> = {
  up: '超预期',
  down: '低于预期',
  flat: '与预期一致',
}

/**
 * Prediction-vs-actual deviation: ▲ when the team out-performed its predicted
 * rank (finished higher), ▼ when it under-performed. The numeral is the
 * absolute rank gap. Color is the colorblind-safe up/down pair from tokens.
 */
export function DeviationCell({
  predictedRank,
  actualRank,
}: DeviationCellProps) {
  const dir = deviationDirection(predictedRank, actualRank)
  const gap = rankGap(predictedRank, actualRank)

  const title =
    dir === 'flat'
      ? LABEL.flat
      : `${LABEL[dir]} ${gap ?? 0} 名（预测第 ${predictedRank} → 实际第 ${actualRank}）`

  return (
    <span className={`deviation deviation--${dir}`} title={title}>
      <span aria-hidden="true">{ARROW[dir]}</span>
      <span>{dir === 'flat' ? '0' : gap}</span>
    </span>
  )
}
