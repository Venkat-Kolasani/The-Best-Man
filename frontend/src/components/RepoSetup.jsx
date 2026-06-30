import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '../lib/api.js'

const EMPTY_SUMMARY = null

function getStatusClass(status) {
  return `status-chip is-${status || 'idle'}`
}

export function RepoSetup({ repo, onRepoChange, onIngestionStart }) {
  const [job, setJob] = useState(null)
  const [summary, setSummary] = useState(EMPTY_SUMMARY)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const pollTimeoutRef = useRef(null)

  useEffect(() => {
    return () => {
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current)
      }
    }
  }, [])

  const stopPolling = () => {
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
  }

  const repoIsValid = repo.owner.trim() && repo.repo.trim()

  const pollJobStatus = async (owner, repoName, jobId) => {
    try {
      const nextJob = await apiRequest(`/repos/${owner}/${repoName}/ingest/${jobId}`)
      setJob(nextJob)

      if (nextJob.status === 'done' || nextJob.status === 'failed') {
        stopPolling()
        setSummary(nextJob.summary || null)
        if (nextJob.status === 'failed') {
          setError(nextJob.error || 'Ingestion failed before the job completed.')
        }
        return
      }

      pollTimeoutRef.current = window.setTimeout(() => {
        pollJobStatus(owner, repoName, jobId)
      }, 3000)
    } catch (pollError) {
      stopPolling()
      const message =
        pollError.message && pollError.message.includes('was not found')
          ? 'This job no longer exists. The backend may have restarted. Start ingestion again.'
          : pollError.message || 'Unable to read ingestion job status.'
      setError(message)
      setJob((currentJob) =>
        currentJob
          ? {
              ...currentJob,
              status: 'failed',
              error: message,
            }
          : null,
      )
    }
  }

  const handleSubmit = async () => {
    if (!repoIsValid || isSubmitting) {
      return
    }

    const owner = repo.owner.trim()
    const repoName = repo.repo.trim()

    stopPolling()
    setError('')
    setSummary(EMPTY_SUMMARY)
    setIsSubmitting(true)

    try {
      const ingestJob = await apiRequest(`/repos/${owner}/${repoName}/ingest`, {
        method: 'POST',
      })
      setJob(ingestJob)
      onIngestionStart({ owner, repo: repoName })
      pollTimeoutRef.current = window.setTimeout(() => {
        pollJobStatus(owner, repoName, ingestJob.job_id)
      }, 1200)
    } catch (submitError) {
      setError(submitError.message || 'Unable to start repository ingestion.')
      setJob(null)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2>Repository Setup</h2>
          <p className="panel-subtitle">
            Point the frontend at a GitHub repository, kick off ingestion, and watch the background
            job settle into a memory graph.
          </p>
        </div>
        {job ? <span className={getStatusClass(job.status)}>{job.status}</span> : null}
      </div>

      <div className="field-grid">
        <div className="field">
          <label htmlFor="owner-input">GitHub owner</label>
          <input
            id="owner-input"
            value={repo.owner}
            onChange={(event) => onRepoChange({ ...repo, owner: event.target.value })}
            placeholder="Venkat-Kolasani"
          />
        </div>

        <div className="field">
          <label htmlFor="repo-input">Repository name</label>
          <input
            id="repo-input"
            value={repo.repo}
            onChange={(event) => onRepoChange({ ...repo, repo: event.target.value })}
            placeholder="MemoryWeave"
          />
        </div>
      </div>

      <div className="action-row">
        <button
          type="button"
          className="primary-button"
          onClick={handleSubmit}
          disabled={!repoIsValid || isSubmitting || job?.status === 'running'}
        >
          {isSubmitting ? 'Starting ingest...' : 'Ingest repository'}
        </button>

        {job?.status === 'queued' || job?.status === 'running' ? (
          <div className="progress-inline" aria-live="polite">
            <span>Polling background job</span>
            <span className="progress-dots" aria-hidden="true">
              <span></span>
              <span></span>
              <span></span>
            </span>
          </div>
        ) : null}
      </div>

      {job ? (
        <div className="stack">
          <div className="meta-chip">Job ID: {job.job_id}</div>
        </div>
      ) : null}

      {summary ? (
        <>
          <div className="summary-grid">
            <div className="stat-card">
              <span>Commits ingested</span>
              <strong>{summary.commits_ingested}</strong>
            </div>
            <div className="stat-card">
              <span>PRs ingested</span>
              <strong>{summary.prs_ingested}</strong>
            </div>
            <div className="stat-card">
              <span>Comments ingested</span>
              <strong>{summary.comments_ingested}</strong>
            </div>
          </div>

          <h3 className="footer-copy">Skipped items</h3>
          {summary.skipped?.length ? (
            <ul className="skipped-list">
              {summary.skipped.map((item, index) => (
                <li className="skipped-item" key={`${item.source_id}-${index}`}>
                  <strong>{item.source_type}: {item.source_id}</strong>
                  <p>{item.reason}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">No skipped items were reported for this run.</p>
          )}
        </>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}
    </section>
  )
}
