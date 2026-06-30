import { useState } from 'react'
import { apiRequest } from '../lib/api.js'

export function DecisionLogPanel({ repo }) {
  const [content, setContent] = useState('')
  const [decisions, setDecisions] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const canSubmit = Boolean(repo?.owner && repo?.repo && content.trim())

  const handleSubmit = async () => {
    if (!repo || !canSubmit || isSubmitting) {
      return
    }

    setIsSubmitting(true)
    setError('')
    setSuccess('')

    try {
      await apiRequest(`/repos/${repo.owner}/${repo.repo}/decisions`, {
        method: 'POST',
        body: JSON.stringify({ content: content.trim() }),
      })

      setDecisions((current) => [
        {
          id: crypto.randomUUID(),
          content: content.trim(),
          repo: `${repo.owner}/${repo.repo}`,
        },
        ...current,
      ])
      setContent('')
      setSuccess('Decision recorded for this session.')
    } catch (requestError) {
      setError(requestError.message || 'Unable to log the manual decision.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2>Decision Log</h2>
          <p className="panel-subtitle">
            Capture a human judgment call, rollout note, or architectural correction and push it
            into the same repository dataset.
          </p>
        </div>
      </div>

      <div className="textarea-field">
        <label htmlFor="manual-decision">Manual decision entry</label>
        <textarea
          id="manual-decision"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          placeholder="Example: We kept the graph schema minimal for the demo and postponed user-level ACLs until after the judging round."
        />
      </div>

      <div className="action-row">
        <button
          type="button"
          className="secondary-button"
          onClick={handleSubmit}
          disabled={!canSubmit || isSubmitting}
        >
          {isSubmitting ? 'Logging...' : 'Log Decision'}
        </button>
      </div>

      {!repo ? (
        <p className="inline-note">Select a repository before adding manual decisions.</p>
      ) : null}

      {success ? <div className="success-banner">{success}</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      <h3 className="footer-copy">Session decision trail</h3>
      {decisions.length ? (
        <ul className="decision-list">
          {decisions.map((decision) => (
            <li className="decision-item" key={decision.id}>
              <strong>{decision.repo}</strong>
              <p>{decision.content}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-state">No manual decisions have been logged in this browser session yet.</p>
      )}
    </section>
  )
}
