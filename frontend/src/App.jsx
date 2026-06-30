import { useState } from 'react'
import './App.css'
import { DecisionLogPanel } from './components/DecisionLogPanel.jsx'
import { ForgetControl } from './components/ForgetControl.jsx'
import { ImproveFeedback } from './components/ImproveFeedback.jsx'
import { RecallPanel } from './components/RecallPanel.jsx'
import { RepoSetup } from './components/RepoSetup.jsx'

function App() {
  const [repo, setRepo] = useState({ owner: '', repo: '' })
  const [activeRepo, setActiveRepo] = useState(null)
  const [lastRecall, setLastRecall] = useState(null)

  const handleRepoChange = (nextRepo) => {
    setRepo(nextRepo)
  }

  const handleIngestionStart = (nextRepo) => {
    setActiveRepo(nextRepo)
    setLastRecall(null)
  }

  const repoLabel = activeRepo ? `${activeRepo.owner}/${activeRepo.repo}` : 'No repository selected yet'

  return (
    <div className="app-shell">
      <header className="hero-banner">
        <div className="hero-copy">
          <p className="eyebrow">The Best Man</p>
          <h1>Repository Memory Console</h1>
          <p className="hero-text">
            Ingest a GitHub repository, ask timeline-aware questions about its history, and
            capture the decisions that shaped it.
          </p>
        </div>
        <div className="hero-status">
          <span className="status-label">Active dataset</span>
          <strong>{repoLabel}</strong>
          <p>Backed by Cognee memory, GitHub ingestion, and a lightweight demo control plane.</p>
        </div>
      </header>

      <main className="dashboard-grid">
        <section className="dashboard-column primary-column">
          <RepoSetup
            repo={repo}
            onRepoChange={handleRepoChange}
            onIngestionStart={handleIngestionStart}
          />

          <RecallPanel
            repo={activeRepo}
            onRecallComplete={setLastRecall}
          />

          {lastRecall?.answer ? (
            <ImproveFeedback repo={activeRepo} recall={lastRecall} />
          ) : null}
        </section>

        <section className="dashboard-column secondary-column">
          <DecisionLogPanel repo={activeRepo} />
          <ForgetControl
            repo={activeRepo}
            onForgot={() => {
              setLastRecall(null)
            }}
          />
        </section>
      </main>
    </div>
  )
}

export default App
