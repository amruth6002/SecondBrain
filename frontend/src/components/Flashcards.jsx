import { useState, useEffect, useMemo, useCallback } from "react";
import { reviewFlashcard } from "../api/client";
import Icon from "./Icon";

const BLOOM_COLORS = {
    remember: { color: "var(--success)", bg: "var(--success-dim)" },
    understand: { color: "var(--accent)", bg: "var(--accent-dim)" },
    apply: { color: "var(--warning)", bg: "var(--warning-dim)" },
    analyze: { color: "var(--error)", bg: "var(--error-dim)" },
};

const BLOOM_LEVELS = ["remember", "understand", "apply", "analyze"];

function exportCSV(flashcards) {
    const header = ["Question", "Answer", "Bloom Level", "Source Excerpt"];
    const rows = flashcards.map((c) => [
        `"${(c.question || "").replace(/"/g, '""')}"`,
        `"${(c.answer || "").replace(/"/g, '""')}"`,
        `"${c.bloom_level || ""}"`,
        `"${(c.source_excerpt || "").replace(/"/g, '""')}"`,
    ]);
    const csv = [header, ...rows].map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "flashcards.csv";
    a.click();
    URL.revokeObjectURL(url);
}

export default function Flashcards({ flashcards, exploreState, onClearExplore, onUpdate, onToast }) {
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isFlipped, setIsFlipped] = useState(false);
    const [reviewing, setReviewing] = useState(false);
    const [filterBloom, setFilterBloom] = useState(null);
    const [isCollapsed, setIsCollapsed] = useState(false);

    const filtered = useMemo(() =>
        filterBloom ? flashcards.filter((c) => c.bloom_level === filterBloom) : flashcards,
        [flashcards, filterBloom]
    );

    // Reset index when filter changes
    useEffect(() => {
        /* eslint-disable react-hooks/set-state-in-effect */
        setCurrentIndex(0);
        setIsFlipped(false);
        /* eslint-enable react-hooks/set-state-in-effect */
    }, [filterBloom]);

    // Memoized review handler to fix React dependency warnings and hoisting issues
    const handleReview = useCallback(async (quality) => {
        if (!filtered.length) return;
        const card = filtered[currentIndex];

        setReviewing(true);
        try {
            await reviewFlashcard(card.id, quality);
            if (onUpdate) onUpdate();
        } catch (e) {
            console.error("Flashcard review failed:", e);
        }
        setReviewing(false);
        setIsFlipped(false);
        setCurrentIndex((prev) => (prev + 1) % filtered.length);
    }, [filtered, currentIndex, onUpdate]);

    // Keyboard shortcuts — skip if typing in an input/textarea
    useEffect(() => {
        const onKey = (e) => {
            if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
            if (!filtered.length) return;
            if (e.key === " " || e.key === "ArrowUp" || e.key === "ArrowDown") {
                e.preventDefault();
                setIsFlipped((f) => !f);
            } else if (e.key === "ArrowRight") {
                setIsFlipped(false);
                setCurrentIndex((p) => (p + 1) % filtered.length);
            } else if (e.key === "ArrowLeft") {
                setIsFlipped(false);
                setCurrentIndex((p) => (p - 1 + filtered.length) % filtered.length);
            } else if (e.key === "1" && isFlipped) {
                handleReview(1);
            } else if (e.key === "2" && isFlipped) {
                handleReview(3);
            } else if (e.key === "3" && isFlipped) {
                handleReview(5);
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [filtered, isFlipped, currentIndex, handleReview]);

    if (!flashcards.length) {
        return (
            <div className="card flashcard-card" style={{ position: "relative" }}>
                <div className="flashcard-header">
                    <div className="card-title">
                        <Icon name="cards" />
                        {exploreState ? `Deep Dive: ${exploreState.conceptName}` : "Flashcards"}
                    </div>
                    {exploreState && (
                        <button className="btn" onClick={onClearExplore} style={{ padding: "4px 8px", fontSize: "12px", background: "var(--bg-tertiary)", border: "1px solid var(--border)" }}>
                            <Icon name="xmark" size={12} /> Exit Full Review
                        </button>
                    )}
                </div>
                <div className="empty-state">
                    <Icon name="cards" size={48} className="empty-icon" />
                    <p>{exploreState ? `No flashcards generated for ${exploreState.conceptName} yet.` : "Process content to generate flashcards"}</p>
                </div>
            </div>
        );
    }

    if (!filtered.length) {
        return (
            <div className="card flashcard-card" style={{ position: "relative" }}>
                <div className="flashcard-header">
                    <div className="card-title">
                        <Icon name="cards" />
                        {exploreState ? `Deep Dive: ${exploreState.conceptName}` : "Flashcards"}
                    </div>
                    <div className="flashcard-header-right">
                        {exploreState && (
                            <button className="btn" onClick={onClearExplore} style={{ padding: "4px 8px", fontSize: "12px", background: "var(--bg-tertiary)", border: "1px solid var(--border)" }}>
                                <Icon name="xmark" size={12} /> Exit Deep Dive
                            </button>
                        )}
                        <button className="export-btn" onClick={() => { exportCSV(flashcards); onToast?.("Exported " + flashcards.length + " cards as CSV", "success"); }}>
                            <Icon name="link" size={13} />CSV
                        </button>
                        <button className="collapse-btn" onClick={() => setIsCollapsed(!isCollapsed)} title="Toggle collapse">
                            <Icon name={isCollapsed ? "chevron_down" : "chevron_up"} size={16} />
                        </button>
                    </div>
                </div>
                {!isCollapsed && (
                    <>
                        <BloomFilters active={filterBloom} onChange={setFilterBloom} flashcards={flashcards} />
                        <div className="empty-state" style={{ marginTop: 16 }}>
                            <p>No cards for this Bloom level</p>
                        </div>
                    </>
                )}
            </div>
        );
    }

    const card = filtered[currentIndex];
    const bloom = BLOOM_COLORS[card.bloom_level] || BLOOM_COLORS.understand;

    const goTo = (dir) => {
        setIsFlipped(false);
        setCurrentIndex((prev) =>
            dir === "next"
                ? (prev + 1) % filtered.length
                : (prev - 1 + filtered.length) % filtered.length
        );
    };

    return (
        <div className="card flashcard-card" style={{ position: "relative" }}>
            <div className="flashcard-header">
                <div className="card-title">
                    <Icon name="cards" />
                    {exploreState ? `Deep Dive: ${exploreState.conceptName}` : "Flashcards"}
                </div>
                <div className="flashcard-header-right">
                    {exploreState && (
                        <button className="btn" onClick={onClearExplore} style={{ padding: "4px 8px", fontSize: "12px", background: "var(--bg-tertiary)", border: "1px solid var(--border)" }}>
                            <Icon name="xmark" size={12} /> Exit Deep Dive
                        </button>
                    )}
                    <span className="card-counter">{currentIndex + 1}/{filtered.length}</span>
                    <button
                        className="export-btn"
                        title="Export as CSV"
                        onClick={() => { exportCSV(flashcards); onToast?.("Exported " + flashcards.length + " cards as CSV", "success"); }}
                    >
                        <Icon name="link" size={13} />
                        CSV
                    </button>
                    <button className="collapse-btn" onClick={() => setIsCollapsed(!isCollapsed)} title="Toggle collapse">
                        <Icon name={isCollapsed ? "chevron_down" : "chevron_up"} size={16} />
                    </button>
                </div>
            </div>

            {!isCollapsed && (
                <>

                    {/* Bloom filter chips */}
                    <BloomFilters active={filterBloom} onChange={setFilterBloom} flashcards={flashcards} />

                    <span className="bloom-badge" style={{ background: bloom.bg, color: bloom.color }}>
                        {card.bloom_level}
                    </span>

                    <div
                        className={`flashcard ${isFlipped ? "flipped" : ""}`}
                        onClick={() => setIsFlipped(!isFlipped)}
                    >
                        <div className="flashcard-inner">
                            <div className="flashcard-front">
                                <p className="flashcard-label">Question</p>
                                <p className="flashcard-text">{card.question}</p>
                                <p className="flashcard-hint">
                                    <Icon name="click" size={12} />
                                    Space or click to reveal
                                </p>
                            </div>
                            <div className="flashcard-back">
                                <p className="flashcard-label">Answer</p>
                                <p className="flashcard-text">{card.answer}</p>
                                {card.source_excerpt && (
                                    <div className="source-excerpt">
                                        <span className="source-excerpt-label">
                                            <Icon name="search" size={11} />
                                            Source
                                        </span>
                                        <p className="source-excerpt-text">&ldquo;{card.source_excerpt}&rdquo;</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {isFlipped && (
                        <div className="review-buttons">
                            <button className="btn-review hard" onClick={() => handleReview(1)} disabled={reviewing}>
                                <kbd>1</kbd> Hard
                            </button>
                            <button className="btn-review medium" onClick={() => handleReview(3)} disabled={reviewing}>
                                <kbd>2</kbd> Medium
                            </button>
                            <button className="btn-review easy" onClick={() => handleReview(5)} disabled={reviewing}>
                                <kbd>3</kbd> Easy
                            </button>
                        </div>
                    )}

                    <div className="flashcard-nav">
                        <button className="btn-nav" onClick={() => goTo("prev")}>
                            <Icon name="arrow_left" size={14} /> Prev
                        </button>
                        <p className="flashcard-shortcut-hint">← → to navigate · Space to flip</p>
                        <button className="btn-nav" onClick={() => goTo("next")}>
                            Next <Icon name="arrow_right" size={14} />
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}

function BloomFilters({ active, onChange, flashcards }) {
    const counts = {};
    flashcards.forEach((c) => { counts[c.bloom_level] = (counts[c.bloom_level] || 0) + 1; });
    return (
        <div className="bloom-filters">
            <button
                className={`bloom-filter-btn ${!active ? "active" : ""}`}
                onClick={() => onChange(null)}
            >
                All <span className="bloom-filter-count">{flashcards.length}</span>
            </button>
            {BLOOM_LEVELS.filter((l) => counts[l]).map((level) => {
                const col = BLOOM_COLORS[level];
                return (
                    <button
                        key={level}
                        className={`bloom-filter-btn ${active === level ? "active" : ""}`}
                        onClick={() => onChange(active === level ? null : level)}
                        style={active === level ? { background: col.bg, borderColor: col.color, color: col.color } : {}}
                    >
                        {level} <span className="bloom-filter-count">{counts[level]}</span>
                    </button>
                );
            })}
        </div>
    );
}
