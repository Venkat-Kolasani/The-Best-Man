import { useState } from 'react'
import { apiRequest } from '../lib/api.js'

function hasGraphEvidence(answerState) {
  return Boolean(
    answerState?.graph?.nodes?.length ||
      answerState?.graph?.edges?.length ||
      answerState?.highlighted?.node_ids?.length ||
      answerState?.highlighted?.edge_ids?.length,
  )
}

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

          {hasGraphEvidence(answerState) ? (
            <>
              <h3 className="footer-copy">Graph evidence used for this answer</h3>

              <div className="evidence-summary">
                <div className="evidence-chip">
                  Nodes shown: {answerState.graph?.nodes?.length || 0}
                </div>
                <div className="evidence-chip">
                  Edges shown: {answerState.graph?.edges?.length || 0}
                </div>
                <div className="evidence-chip is-highlighted">
                  Highlighted nodes: {answerState.highlighted?.node_ids?.length || 0}
                </div>
                <div className="evidence-chip is-highlighted">
                  Highlighted edges: {answerState.highlighted?.edge_ids?.length || 0}
                </div>
              </div>

              {answerState.graph?.nodes?.length ? (
                <>
                  <h4 className="subsection-title">Nodes</h4>
                  <div className="evidence-grid">
                    {answerState.graph.nodes.map((node) => {
                      const isHighlighted = answerState.highlighted?.node_ids?.includes(node.id)
                      return (
                        <article
                          className={`evidence-card${isHighlighted ? ' is-highlighted' : ''}`}
                          key={node.id}
                        >
                          <div className="evidence-card-header">
                            <strong>{node.label}</strong>
                            <span className="evidence-type">{node.type}</span>
                          </div>
                          <p className="evidence-id">Node ID: {node.id}</p>
                          {Object.keys(node.properties || {}).length ? (
                            <dl className="evidence-properties">
                              {Object.entries(node.properties).map(([key, value]) => (
                                <div key={key}>
                                  <dt>{key}</dt>
                                  <dd>{String(value)}</dd>
                                </div>
                              ))}
                            </dl>
                          ) : (
                            <p className="inline-note">No additional node properties were returned.</p>
                          )}
                        </article>
                      )
                    })}
                  </div>
                </>
              ) : null}

              {answerState.graph?.edges?.length ? (
                <>
                  <h4 className="subsection-title">Connections</h4>
                  <ul className="connection-list">
                    {answerState.graph.edges.map((edge, index) => {
                      const isHighlighted =
                        Boolean(edge.id) &&
                        answerState.highlighted?.edge_ids?.includes(edge.id)
                      return (
                        <li
                          className={`connection-item${isHighlighted ? ' is-highlighted' : ''}`}
                          key={`${edge.source}-${edge.target}-${edge.label}-${index}`}
                        >
                          <strong>{edge.label}</strong>
                          <p>
                            {edge.source} {'->'} {edge.target}
                          </p>
                          {edge.id ? <span className="connection-meta">Edge ID: {edge.id}</span> : null}
                        </li>
                      )
                    })}
                  </ul>
                </>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}
    </section>
  )
}
