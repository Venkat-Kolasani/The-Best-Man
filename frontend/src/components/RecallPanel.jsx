import { useState } from 'react'
import { apiRequest } from '../lib/api.js'

export function RecallPanel({ repo, onRecallComplete }) {
  const [query, setQuery] = useState('')
  const [answerState, setAnswerState] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const canAsk = Boolean(repo?.owner && repo?.repo && query.trim())

  const handleAsk = async () => {
    if (!repo || !canAsk || isLoading) {
      return
    }

    setIsLoading(true)
    setError('')

    try {
      const response = await apiRequest(`/repos/${repo.owner}/${repo.repo}/recall`, {
        method: 'POST',
        body: JSON.stringify({ query: query.trim() }),
      })
      setAnswerState(response)
      onRecallComplete(response)
    } catch (requestError) {
      setError(requestError.message || 'Unable to recall repository memory.')
      setAnswerState(null)
      onRecallComplete(null)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2>Recall Panel</h2>
          <p className="panel-subtitle">
            Ask a question that requires the system to connect repository context across commits,
            pull requests, and discussion history.
          </p>
        </div>
      </div>

      <div className="question-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Why did the team shift memory from local storage to a graph-backed approach?"
        />
        <button
          type="button"
          className="primary-button"
          onClick={handleAsk}
          disabled={!canAsk || isLoading}
        >
          {isLoading ? 'Asking...' : 'Ask'}
        </button>
      </div>

      {!repo ? (
        <p className="inline-note">Choose and ingest a repository before sending recall queries.</p>
      ) : null}

      {answerState ? (
        <div className="answer-card">
          <p>{answerState.answer || 'No answer returned.'}</p>

          {Array.isArray(answerState.traversal) && answerState.traversal.length ? (
            <>
              <h3 className="footer-copy">Traversal metadata</h3>
              <ul className="source-list">
                {answerState.traversal.map((item, index) => (
                  <li className="source-item" key={index}>
                    <strong>Traversal node {index + 1}</strong>
                    <p>{JSON.stringify(item)}</p>
                  </li>
                ))}
              </ul>
            </>
          ) : null}

          {answerState.sources ? (
            <>
              <h3 className="footer-copy">Sources</h3>
              <ul className="source-list">
                <li className="source-item">
                  <strong>Recall source</strong>
                  <p>{answerState.sources}</p>
                </li>
              </ul>
            </>
          ) : null}
        </div>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}
    </section>
  )
}
