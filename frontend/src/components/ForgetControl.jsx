import { useState } from 'react'
import { apiRequest } from '../lib/api.js'

export function ForgetControl({ repo, onForgot }) {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const handleForget = async () => {
    if (!repo || isSubmitting) {
      return
    }

    const confirmed = window.confirm(
      `Forget all memory for ${repo.owner}/${repo.repo}? This removes the dataset from Cognee.`,
    )
    if (!confirmed) {
      return
    }

    setIsSubmitting(true)
    setMessage('')
    setError('')

    try {
      await apiRequest(`/repos/${repo.owner}/${repo.repo}/memory`, {
        method: 'DELETE',
      })
      setMessage(`Memory cleared for ${repo.owner}/${repo.repo}.`)
      onForgot?.()
    } catch (requestError) {
      setError(requestError.message || 'Unable to forget repository memory.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2>Forget Control</h2>
          <p className="panel-subtitle">
            Wipe the active repository dataset when you need a clean ingestion run or want to test
            the memory lifecycle end to end.
          </p>
        </div>
      </div>

      <button
        type="button"
        className="danger-button"
        onClick={handleForget}
        disabled={!repo || isSubmitting}
      >
        {isSubmitting ? 'Forgetting...' : 'Delete repository memory'}
      </button>

      <p className="destructive-note">
        This action is destructive. The browser will ask for confirmation before the API call is
        sent.
      </p>

      {message ? <div className="success-banner">{message}</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}
    </section>
  )
}
