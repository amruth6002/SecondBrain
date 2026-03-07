import Icon from "./Icon";

export default function Dashboard({ stats, summary }) {
    const statCards = [
        { icon: "book", label: "Concepts", value: stats.total_concepts || 0, color: "#7c83ff", bg: "rgba(124, 131, 255, 0.12)" },
        { icon: "cards", label: "Flashcards", value: stats.total_flashcards || 0, color: "#34d399", bg: "rgba(52, 211, 153, 0.12)" },
        { icon: "calendar", label: "Due Today", value: stats.due_for_review || 0, color: "#fbbf24", bg: "rgba(251, 191, 36, 0.12)" },
        { icon: "trophy", label: "Mastered", value: stats.mastered || 0, color: "#fb7185", bg: "rgba(251, 113, 133, 0.12)" },
        { icon: "graph", label: "Graph Nodes", value: stats.graph_nodes || 0, color: "#a78bfa", bg: "rgba(167, 139, 250, 0.12)" },
        { icon: "link", label: "Connections", value: stats.graph_edges || 0, color: "#22d3ee", bg: "rgba(34, 211, 238, 0.12)" },
    ];

    return (
        <div className="card dashboard-card">
            <div className="card-title">
                <Icon name="results" />
                Dashboard
            </div>
            <p className="card-description">Overview of your extracted knowledge.</p>

            <div className="stat-grid">
                {statCards.map((s) => (
                    <div key={s.label} className="stat-item">
                        <div
                            className="stat-icon-wrapper"
                            style={{ background: s.bg }}
                        >
                            <Icon name={s.icon} size={18} className="icon" style={{ color: s.color }} />
                        </div>
                        <span className="stat-value" style={{ color: s.color }}>
                            {s.value}
                        </span>
                        <span className="stat-label">{s.label}</span>
                    </div>
                ))}
            </div>

            {summary && (
                <div className="summary-section">
                    <h3 className="summary-heading">
                        <Icon name="summary" size={16} />
                        Content Summary
                    </h3>
                    <p className="summary-text">{summary}</p>
                </div>
            )}
        </div>
    );
}
