import { useState } from 'react'
import { apiRequest } from '../lib/api.js'

export function ImproveFeedback({ repo, recall }) {
  const [vote, setVote] = useState(null)
  const [feedback, setFeedback] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (nextVote) => {
    if (!repo || isSubmitting) {
      return
    }

    setVote(nextVote)
    setIsSubmitting(true)
    setMessage('')
    setError('')

    const prefix =
      nextVote === 'up'
        ? 'Positive feedback: the recall answer was useful.'
        : 'Corrective feedback: the recall answer needs improvement.'
    const extraFeedback = feedback.trim()
    const combinedFeedback = extraFeedback ? `${prefix} ${extraFeedback}` : prefix

    try {
      await apiRequest(`/repos/${repo.owner}/${repo.repo}/improve`, {
        method: 'POST',
        body: JSON.stringify({ feedback: combinedFeedback }),
      })
      setMessage('Feedback sent to the memory improvement endpoint.')
    } catch (requestError) {
      setError(requestError.message || 'Unable to submit memory feedback.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2>Improve Feedback</h2>
          <p className="panel-subtitle">
            Rate the latest answer and optionally add a correction to nudge later recall behavior.
          </p>
        </div>
      </div>

      <p className="feedback-note">
        Latest answer preview: {recall.answer.slice(0, 180)}
        {recall.answer.length > 180 ? '...' : ''}
      </p>

      <div className="feedback-actions">
        <button
          type="button"
          className={`feedback-button ${vote === 'up' ? 'is-active' : ''}`}
          onClick={() => handleSubmit('up')}
          disabled={isSubmitting}
        >
          👍 Helpful
        </button>
        <button
          type="button"
          className={`feedback-button ${vote === 'down' ? 'is-active' : ''}`}
          onClick={() => handleSubmit('down')}
          disabled={isSubmitting}
        >
          👎 Needs work
        </button>
      </div>

      <div className="textarea-field">
        <label htmlFor="feedback-correction">Optional correction or context</label>
        <textarea
          id="feedback-correction"
          value={feedback}
          onChange={(event) => setFeedback(event.target.value)}
          placeholder="Example: Mention that the migration happened after the team proved SQLite could not handle concurrent memory updates."
        />
      </div>

      {message ? <div className="success-banner">{message}</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}
    </section>
  )
}
