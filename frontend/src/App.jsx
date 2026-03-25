import { useState, useCallback, useEffect } from "react";
import Icon from "./components/Icon";
import NotebookView from "./components/NotebookView";
import KnowledgeGraph from "./components/KnowledgeGraph";
import Flashcards from "./components/Flashcards";
import Dashboard from "./components/Dashboard";
import Chatbot from "./components/Chatbot";
import {
  getDashboardStats,
  getNotebooks,
  createNotebook,
  deleteNotebook,
  getKnowledgeGraph,
  getDueFlashcards,
  getAllFlashcards,
} from "./api/client";
import "./index.css";

const NAV_ITEMS = [
  { id: "dashboard", icon: "results", label: "Dashboard" },
  { id: "graph", icon: "graph", label: "Knowledge Graph" },
  { id: "review", icon: "cards", label: "Review" },
];

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [view, setView] = useState("dashboard");
  const [selectedNotebookId, setSelectedNotebookId] = useState(null);
  const [notebooks, setNotebooks] = useState([]);
  const [stats, setStats] = useState({});
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [dueCards, setDueCards] = useState([]);
  const [exploreState, setExploreState] = useState(null);
  const [toasts, setToasts] = useState([]);

  const refreshNotebooks = useCallback(async () => {
    try { setNotebooks(await getNotebooks()); } catch {}
  }, []);

  const refreshStats = useCallback(async () => {
    try { setStats(await getDashboardStats()); } catch {}
  }, []);

  const refreshGraph = useCallback(async () => {
    try { setGraphData(await getKnowledgeGraph()); } catch {}
  }, []);

  const refreshDueCards = useCallback(async () => {
    try { setDueCards(await getDueFlashcards()); } catch {}
  }, []);

  useEffect(() => {
    refreshNotebooks();
    refreshStats();
  }, [refreshNotebooks, refreshStats]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme((prev) => (prev === "dark" ? "light" : "dark"));

  const addToast = useCallback((message, type = "info") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);

  const handleCreateNotebook = async () => {
    try {
      const nb = await createNotebook("Untitled Notebook");
      await refreshNotebooks();
      setSelectedNotebookId(nb.id);
      setView("notebook");
      addToast("Notebook created", "success");
    } catch { addToast("Failed to create notebook", "error"); }
  };

  const handleSidebarClick = (nbId) => {
    setSelectedNotebookId(nbId);
    setView("notebook");
  };

  const handleDeleteNotebook = async (nbId, e) => {
    e.stopPropagation();
    try {
      await deleteNotebook(nbId);
      await refreshNotebooks();
      if (selectedNotebookId === nbId) {
        setSelectedNotebookId(null);
        setView("dashboard");
      }
      addToast("Notebook deleted", "success");
    } catch { addToast("Failed to delete notebook", "error"); }
  };

  const handleExploreConcept = async (conceptId, conceptName) => {
    try {
      addToast(`Deep diving into ${conceptName} and its connections...`, "info");
      
      const [allCards, globalGraph] = await Promise.all([
        getAllFlashcards(),
        getKnowledgeGraph()
      ]);

      const connectedIds = new Set([conceptId]);
      globalGraph.edges.forEach(edge => {
        const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
        if (sourceId === conceptId) connectedIds.add(targetId);
        if (targetId === conceptId) connectedIds.add(sourceId);
      });

      const filtered = allCards.filter(c => connectedIds.has(c.concept_id));
      setExploreState({ conceptId, conceptName, cards: filtered, isExpanded: true, totalConcepts: connectedIds.size });
      setView("review");
    } catch {
      addToast("Failed to load concept flashcards", "error");
    }
  };

  const handleNavClick = (navId) => {
    setView(navId);
    setSelectedNotebookId(null);
    setExploreState(null); // Clear explore state on nav change
    if (navId === "graph") refreshGraph();
    if (navId === "review") refreshDueCards();
    if (navId === "dashboard") refreshStats();
  };

  const pageMeta = {
    dashboard: { title: "Dashboard", subtitle: "Your learning overview" },
    notebook: { title: notebooks.find(n => n.id === selectedNotebookId)?.name || "Notebook", subtitle: "Manage content and extract knowledge" },
    graph: { title: "Knowledge Graph", subtitle: "All concepts across your notebooks" },
    review: { title: "Flashcard Review", subtitle: "Due cards for spaced repetition" },
  };
  const meta = pageMeta[view] || pageMeta.dashboard;

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
              onClick={() => handleNavClick(item.id)}
            >
              <Icon name={item.icon} size={18} className="nav-icon" />
              {item.label}
            </button>
          ))}
        </nav>

        {/* Notebooks Section */}
        <div className="notebooks-section">
          <div className="notebooks-header">
            <p className="sidebar-label">Notebooks</p>
            <button className="new-notebook-btn" onClick={handleCreateNotebook} title="New Notebook">
              <Icon name="text" size={14} />
              <span>New</span>
            </button>
          </div>
          {notebooks.length === 0 ? (
            <p className="sidebar-empty">No notebooks yet</p>
          ) : (
            <div className="notebook-list">
              {notebooks.map((nb) => (
                <div
                  key={nb.id}
                  className={`notebook-item ${view === "notebook" && selectedNotebookId === nb.id ? "active" : ""}`}
                >
                  <button
                    className="notebook-load-area"
                    onClick={() => handleSidebarClick(nb.id)}
                    title={nb.name}
                  >
                    <Icon name="book" size={13} className="notebook-icon" />
                    <span className="notebook-item-text">{nb.name}</span>
                    {nb.block_count > 0 && <span className="notebook-block-count">{nb.block_count}</span>}
                  </button>
                  <button
                    className="notebook-del-btn"
                    onClick={(e) => handleDeleteNotebook(nb.id, e)}
                    title="Delete notebook"
                  >
                    <Icon name="xmark" size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <p>Built for AI Unlocked 2026</p>
          <p className="tech-stack">Azure AI · Phi-4 · Knowledge Agents</p>
        </div>
      </aside>

      {/* Mobile Bottom Nav */}
      <nav className="mobile-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${view === item.id ? "active" : ""}`}
            onClick={() => handleNavClick(item.id)}
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

        <div className="content-area" key={view === "notebook" ? `nb-${selectedNotebookId}` : view}>
          {/* Dashboard */}
          {view === "dashboard" && (
            <div className="results-layout">
              <Dashboard 
                stats={stats} 
                summary={stats.summary || ""} 
                notebooks={notebooks} 
                onNotebookClick={handleSidebarClick} 
              />
              {notebooks.length === 0 && (
                <div className="card">
                  <div className="empty-state">
                    <Icon name="book" size={48} className="empty-icon" />
                    <p>Create your first notebook to get started</p>
                    <button className="btn btn-primary" onClick={handleCreateNotebook} style={{ marginTop: "1rem" }}>
                      <Icon name="text" size={16} /> New Notebook
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Notebook View */}
          {view === "notebook" && selectedNotebookId && (
            <NotebookView
              notebookId={selectedNotebookId}
              onToast={addToast}
              onRefresh={() => { refreshNotebooks(); refreshStats(); }}
              onNodeExplore={handleExploreConcept}
            />
          )}

          {/* Knowledge Graph */}
          {view === "graph" && (
            <KnowledgeGraph 
              nodes={graphData.nodes || []} 
              edges={graphData.edges || []} 
              onNodeExplore={handleExploreConcept}
            />
          )}

          {/* Review */}
          {view === "review" && (
            <Flashcards
              flashcards={exploreState ? exploreState.cards : dueCards}
              exploreState={exploreState}
              onClearExplore={() => setExploreState(null)}
              onToast={addToast}
              onUpdate={() => { refreshDueCards(); refreshStats(); }}
            />
          )}
        </div>
      </div>

      {/* Toast notifications */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <Icon name={t.type === "success" ? "check" : t.type === "error" ? "xmark" : "pipeline"} size={14} />
            <span>{t.message}</span>
            <button className="toast-close" onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}>
              <Icon name="xmark" size={12} />
            </button>
          </div>
        ))}
      </div>

      {/* Floating Chatbot */}
      <Chatbot notebookId={view === "notebook" ? selectedNotebookId : null} />
    </div>
  );
}
