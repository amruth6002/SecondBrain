import { useState, useCallback, useEffect } from "react";
import Icon from "./components/Icon";
import Upload from "./components/Upload";
import AgentPipeline from "./components/AgentPipeline";
import KnowledgeGraph from "./components/KnowledgeGraph";
import Flashcards from "./components/Flashcards";
import Dashboard from "./components/Dashboard";
import Concepts from "./components/Concepts";
import {
  processText,
  processPDF,
  processYouTube,
  subscribePipelineStatus,
  getDashboardStats,
  getLatestResults,
  getSessions,
  getSession,
  deleteSession,
} from "./api/client";
import "./index.css";

const NAV_ITEMS = [
  { id: "upload", icon: "upload", label: "Upload", desc: "Add new content" },
  { id: "pipeline", icon: "pipeline", label: "Pipeline", desc: "Agent processing" },
  { id: "results", icon: "results", label: "Results", desc: "View insights" },
];

const PAGE_META = {
  upload: { title: "Upload Content", subtitle: "Feed your brain with knowledge from any source" },
  pipeline: { title: "Agent Pipeline", subtitle: "Watch your AI agents process in real-time" },
  results: { title: "Results", subtitle: "Your extracted knowledge at a glance" },
};

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [view, setView] = useState("upload");
  const [isProcessing, setIsProcessing] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState({
    stage: "idle",
    progress: 0,
    message: "",
  });
  const [result, setResult] = useState(null);
  const [stats, setStats] = useState({});
  const [error, setError] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [sessions, setSessions] = useState([]);

  // Load session history on mount and after each new process
  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await getSessions());
    } catch (err) {
      console.warn("Silent fallback: Failed to fetch initial sessions", err);
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  // Sync theme with document attribute and localStorage
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const loadSession = async (sessionId) => {
    try {
      const res = await getSession(sessionId);
      setResult(res);
      const s = await getDashboardStats();
      setStats(s);
      setView("results");
      addToast("Session loaded", "success");
    } catch (err) {
      console.error("Failed to load the specific session data:", err);
      addToast("Failed to load session", "error");
    }
  };

  const handleDeleteSession = async (sessionId, e) => {
    e.stopPropagation();
    try {
      await deleteSession(sessionId);
      await refreshSessions();
      // Clear current result if we deleted the active session
      if (result?.session_id === sessionId) {
        setResult(null);
        setStats({});
      }
      addToast("Session deleted", "success");
    } catch (err) {
      console.error("Failed to delete session:", err);
      addToast("Failed to delete session", "error");
    }
  };

  const addToast = useCallback((message, type = "info") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);

  const handleProcess = async ({ type, data }) => {
    setIsProcessing(true);
    setError(null);
    setView("pipeline");
    setPipelineStatus({ stage: "planner", progress: 5, message: "Starting..." });

    try {
      // Fire the pipeline (returns immediately; backend runs it in the background)
      if (type === "text") await processText(data);
      else if (type === "pdf") await processPDF(data);
      else if (type === "youtube") await processYouTube(data);
    } catch (e) {
      setError(e.message || "Failed to start processing");
      setPipelineStatus({ stage: "error", progress: 0, message: e.message || "Failed to start" });
      setIsProcessing(false);
      return;
    }

    // Track progress via SSE; fetch result when pipeline completes
    subscribePipelineStatus(async (status) => {
      setPipelineStatus(status);

      if (status.stage === "complete") {
        try {
          const res = await getLatestResults();
          setResult(res);
          const s = await getDashboardStats().catch(() => null);
          if (s) setStats(s);
          await refreshSessions();
          setView("results");
        } catch (err) {
          console.warn("Failed to fetch results after pipeline complete", err);
        } finally {
          setIsProcessing(false);
        }
      } else if (status.stage === "error") {
        setError(status.message || "Processing failed");
        setIsProcessing(false);
      }
    });
  };

  const meta = PAGE_META[view] || PAGE_META.upload;

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">S</div>
          <span className="brand-text">SecondBrain</span>
          <span className="brand-badge">AI</span>
        </div>

        <p className="sidebar-label">Navigation</p>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? "active" : ""}`}
              onClick={() => setView(item.id)}
            >
              <Icon name={item.icon} size={18} className="nav-icon" />
              {item.label}
            </button>
          ))}
        </nav>

        {sessions.length > 0 && (
          <div className="session-history">
            <p className="sidebar-label">Recent Sessions</p>
            {sessions.slice(0, 6).map((s) => (
              <div key={s.id} className="session-item">
                <button
                  className="session-load-area"
                  onClick={() => loadSession(s.id)}
                  title={s.summary || s.title}
                >
                  <Icon name="book" size={13} className="session-icon" />
                  <span className="session-item-text">{s.title}</span>
                </button>
                <button
                  className="session-del-btn"
                  onClick={(e) => handleDeleteSession(s.id, e)}
                  title="Delete session"
                >
                  <Icon name="xmark" size={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="sidebar-footer">
          <p>Built for AI Unlocked 2026</p>
          <p className="tech-stack">Azure AI · Phi-4 · AutoGen</p>
        </div>
      </aside>

      {/* Mobile Bottom Nav */}
      <nav className="mobile-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${view === item.id ? "active" : ""}`}
            onClick={() => setView(item.id)}
          >
            <Icon name={item.icon} size={18} className="nav-icon" />
            {item.label}
          </button>
        ))}
      </nav>

      {/* Main Content */}
      <div className="main-content">
        <div className="page-header">
          <div className="page-header-text">
            <h1 className="page-title">{meta.title}</h1>
            <p className="page-subtitle">{meta.subtitle}</p>
          </div>
          <button className="theme-toggle" onClick={toggleTheme} title="Toggle Dark/Light Mode">
            <Icon name={theme === "dark" ? "sun" : "moon"} size={20} />
          </button>
        </div>

        <div className="content-area" key={view}>
          {/* Error Banner */}
          {error && (
            <div className="error-banner">
              <Icon name="exclamation" size={16} />
              <span className="error-text">{error}</span>
              <button className="error-close" onClick={() => setError(null)}>
                <Icon name="xmark" size={14} />
              </button>
            </div>
          )}

          {view === "upload" && (
            <Upload onProcess={handleProcess} isProcessing={isProcessing} />
          )}

          {view === "pipeline" && (
            <div className="pipeline-split">
              <AgentPipeline status={pipelineStatus} variant="stepper" />
              <AgentPipeline status={pipelineStatus} variant="feed" />
            </div>
          )}

          {view === "results" && result && (
            <div className="results-layout">
              <Dashboard stats={stats} summary={result.summary} />
              <KnowledgeGraph
                nodes={result.graph_nodes || []}
                edges={result.graph_edges || []}
              />
              <Flashcards
                flashcards={result.flashcards || []}
                onToast={addToast}
                onUpdate={async () => {
                  const s = await getDashboardStats();
                  setStats(s);
                }}
              />
              <Concepts concepts={result.concepts || []} />
            </div>
          )}

          {view === "results" && !result && (
            <div className="card">
              <div className="empty-state">
                <Icon name="results" size={48} className="empty-icon" />
                <p>No results yet. Upload some content to get started.</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Toast notifications */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <Icon
              name={t.type === "success" ? "check" : t.type === "error" ? "xmark" : "pipeline"}
              size={14}
            />
            <span>{t.message}</span>
            <button className="toast-close" onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}>
              <Icon name="xmark" size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
