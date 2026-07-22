import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getPredictionsIndex,
  type PredictionIndexEntry,
} from '../../lib/data'
import { formatDateTime } from '../../lib/format'
import './prediction.css'

export default function PredictionsPage() {
  const navigate = useNavigate()
  const [predictions, setPredictions] = useState<PredictionIndexEntry[] | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getPredictionsIndex()
      .then((rows) => {
        if (active) setPredictions(rows)
      })
      .catch((reason: unknown) => {
        if (active)
          setError(
            reason instanceof Error ? reason.message : '预测数据加载失败',
          )
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="page-enter prediction-page">
      <section className="wrap phead prediction-index__head">
        <span className="eyebrow eyebrow--oxford">PRE-MATCH FORECAST</span>
        <h1 className="display">赛前预测</h1>
        <p className="subtle">
          把公开参赛名单与赛前积分、分级历史奖牌连接起来，以积分排序和奖牌排序两种视角预测正式队伍名次。
        </p>
      </section>

      <section className="wrap prediction-index__body">
        {error ? (
          <div className="state" role="alert">
            <p className="state__title">无法加载预测</p>
            <p>{error}</p>
          </div>
        ) : predictions === null ? (
          <div className="state" role="status">
            预测加载中…
          </div>
        ) : predictions.length === 0 ? (
          <div className="state">暂无即将举行比赛的公开名单。</div>
        ) : (
          <div className="prediction-index__list">
            {predictions.map((prediction) => {
              return (
                <button
                  type="button"
                  className="prediction-index__row"
                  key={prediction.slug}
                  onClick={() => navigate(`/prediction/${prediction.slug}`)}
                >
                  <span className="prediction-index__date tnum">
                    {formatDateTime(prediction.startAt)}
                  </span>
                  <span className="prediction-index__main">
                    <b>{prediction.shortTitle}</b>
                    <small>{prediction.title}</small>
                  </span>
                  <span className="prediction-index__metric">
                    <b className="tnum">{prediction.teamCount}</b>
                    <small>支队伍</small>
                  </span>
                  <span className="prediction-index__arrow" aria-hidden="true">
                    →
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
