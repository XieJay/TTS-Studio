import { Component, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Playground from './pages/Playground'
import Settings from './pages/Settings'
import Studio from './pages/Studio'
import Voices from './pages/Voices'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-3xl p-8">
          <h1 className="text-lg font-semibold text-danger">页面出错了</h1>
          <pre className="mt-3 overflow-auto rounded-lg border border-border bg-surface-2 p-3 text-xs">{String(this.state.error.stack || this.state.error)}</pre>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <Layout>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/playground" element={<Playground />} />
          <Route path="/studio/:taskId" element={<Studio />} />
          <Route path="/voices" element={<Voices />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
    </Layout>
  )
}
