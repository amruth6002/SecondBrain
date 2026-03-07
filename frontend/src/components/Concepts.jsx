import { useState, useMemo } from "react";
import Icon from "./Icon";

const CATEGORY_COLORS = {
    definition: "#7c83ff",
    theorem: "#fb7185",
    process: "#34d399",
    formula: "#fbbf24",
    example: "#a78bfa",
    principle: "#22d3ee",
    default: "#7c83ff",
};

const IMPORTANCE_LABEL = { high: "High", medium: "Med", low: "Low" };
const IMPORTANCE_COLOR = {
    high: { color: "#fb7185", bg: "rgba(251,113,133,0.12)" },
    medium: { color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
    low: { color: "#34d399", bg: "rgba(52,211,153,0.10)" },
};

export default function Concepts({ concepts }) {
    const [search, setSearch] = useState("");
    const [filterCat, setFilterCat] = useState(null);
    const [isCollapsed, setIsCollapsed] = useState(false);

    const categories = useMemo(() => {
        const cats = [...new Set(concepts.map((c) => c.category).filter(Boolean))];
        return cats.sort();
    }, [concepts]);

    const filtered = useMemo(() => {
        const q = search.toLowerCase();
        return concepts.filter((c) => {
            const matchCat = !filterCat || c.category === filterCat;
            const matchQ = !q || c.name.toLowerCase().includes(q) || c.definition.toLowerCase().includes(q);
            return matchCat && matchQ;
        });
    }, [concepts, search, filterCat]);

    if (!concepts.length) {
        return (
            <div className="card concepts-card">
                <div className="card-title">
                    <Icon name="book" />
                    Concepts
                </div>
                <div className="empty-state">
                    <Icon name="book" size={48} className="empty-icon" />
                    <p>Process content to extract concepts</p>
                </div>
            </div>
        );
    }

    return (
        <div className="card concepts-card">
            <div className="concepts-header">
                <div className="card-title">
                    <Icon name="book" />
                    Concepts
                    <span className="concepts-count">{filtered.length}/{concepts.length}</span>
                    <button className="collapse-btn" onClick={() => setIsCollapsed(!isCollapsed)} title="Toggle Collapse">
                        <Icon name={isCollapsed ? "chevron_down" : "chevron_up"} size={16} />
                    </button>
                </div>

                {/* Search */}
                {!isCollapsed && (
                    <div className="concepts-search-wrap">
                        <Icon name="search" size={14} className="concepts-search-icon" />
                        <input
                            className="concepts-search"
                            placeholder="Search concepts..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                        {search && (
                            <button className="concepts-search-clear" onClick={() => setSearch("")}>
                                <Icon name="xmark" size={12} />
                            </button>
                        )}
                    </div>
                )}
            </div>

            {!isCollapsed && (
                <>

                    {/* Category filters */}
                    <div className="category-filters">
                        <button
                            className={`cat-filter-btn ${!filterCat ? "active" : ""}`}
                            onClick={() => setFilterCat(null)}
                        >
                            All
                        </button>
                        {categories.map((cat) => (
                            <button
                                key={cat}
                                className={`cat-filter-btn ${filterCat === cat ? "active" : ""}`}
                                onClick={() => setFilterCat(filterCat === cat ? null : cat)}
                                style={filterCat === cat ? {
                                    background: `${CATEGORY_COLORS[cat] || CATEGORY_COLORS.default}22`,
                                    borderColor: CATEGORY_COLORS[cat] || CATEGORY_COLORS.default,
                                    color: CATEGORY_COLORS[cat] || CATEGORY_COLORS.default,
                                } : {}}
                            >
                                <span
                                    className="cat-dot"
                                    style={{ background: CATEGORY_COLORS[cat] || CATEGORY_COLORS.default }}
                                />
                                {cat}
                            </button>
                        ))}
                    </div>

                    {/* Concept cards grid */}
                    <div className="concepts-grid">
                        {filtered.map((concept) => {
                            const color = CATEGORY_COLORS[concept.category] || CATEGORY_COLORS.default;
                            const imp = IMPORTANCE_COLOR[concept.importance] || IMPORTANCE_COLOR.medium;
                            return (
                                <div
                                    key={concept.id}
                                    className="concept-card"
                                    style={{ borderTopColor: color }}
                                >
                                    <div className="concept-card-header">
                                        <h4 className="concept-name">{concept.name}</h4>
                                        <div className="concept-badges">
                                            <span
                                                className="concept-badge"
                                                style={{ color, borderColor: color }}
                                            >
                                                {concept.category || "general"}
                                            </span>
                                            <span
                                                className="concept-badge"
                                                style={{ color: imp.color, borderColor: imp.color, background: imp.bg }}
                                            >
                                                {IMPORTANCE_LABEL[concept.importance] || "Med"}
                                            </span>
                                        </div>
                                    </div>

                                    <p className="concept-definition">{concept.definition}</p>

                                    {concept.related_concepts?.length > 0 && (
                                        <div className="concept-related">
                                            <span className="concept-related-label">Related:</span>
                                            {concept.related_concepts.slice(0, 3).map((r, i) => (
                                                <span key={i} className="concept-related-tag">{r}</span>
                                            ))}
                                        </div>
                                    )}

                                    {concept.source_context && (
                                        <p className="concept-source">
                                            &ldquo;{concept.source_context.slice(0, 120)}{concept.source_context.length > 120 ? "…" : ""}&rdquo;
                                        </p>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {filtered.length === 0 && (
                        <div className="concepts-empty">
                            <Icon name="search" size={24} className="empty-icon" />
                            <p>No concepts match your search</p>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
