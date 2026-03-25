import React from "react";
import KnowledgeGraph from "./KnowledgeGraph";
import Flashcards from "./Flashcards";

const DeepDive = ({ exploreState, onClearExplore, onReview, setExploreState }) => {
    
    // We get the active node from the traversal array
    const activeNode = exploreState.traversalNodes[exploreState.activeIndex] || exploreState.traversalNodes[0];
    
    // Filter flashcards specifically for this ONE active node so they are tested sequentially
    const activeCards = exploreState.cards.filter(c => c.concept_id === activeNode?.id);

    const handleNextNode = () => {
        if (exploreState.activeIndex < exploreState.traversalNodes.length - 1) {
            setExploreState(prev => ({ ...prev, activeIndex: prev.activeIndex + 1 }));
        }
    };

    const handlePrevNode = () => {
        if (exploreState.activeIndex > 0) {
            setExploreState(prev => ({ ...prev, activeIndex: prev.activeIndex - 1 }));
        }
    };

    const handleNodeClick = (node) => {
        const idx = exploreState.traversalNodes.findIndex(n => n.id === node.id);
        if (idx !== -1) {
            setExploreState(prev => ({ ...prev, activeIndex: idx }));
        }
    };

    return (
        <div style={{ display: "flex", flexDirection: "row", height: "100%", width: "100%" }}>
            
            {/* Left Pane: Curated Cluster Knowledge Graph */}
            <div style={{ flex: "1", borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
                <div style={{ padding: "16px", borderBottom: "1px solid var(--border)", background: "var(--bg-surface)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <h3 style={{ margin: 0, fontSize: "14px", color: "var(--text)" }}>Guided Mastery</h3>
                    <button className="btn" onClick={onClearExplore} style={{ padding: "4px 10px", fontSize: "12px", background: "var(--bg-tertiary)" }}>
                        Exit Mastery Mode
                    </button>
                </div>
                <div style={{ flex: 1, position: "relative" }}>
                    <KnowledgeGraph 
                        graphData={exploreState.clusterGraph} 
                        onNodeClick={handleNodeClick}
                        hidePanel={true}
                    />
                </div>
            </div>

            {/* Right Pane: Sequential Flashcard Review */}
            <div style={{ flex: "1", display: "flex", flexDirection: "column", overflowY: "auto", background: "var(--bg-default)", padding: "24px" }}>
                
                {/* Concept Header */}
                <div className="card" style={{ marginBottom: "24px", padding: "20px", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--bg-surface)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                        <h2 style={{ margin: 0, fontSize: "20px", color: "var(--primary)" }}>{activeNode?.id}</h2>
                        <div style={{ fontSize: "12px", color: "var(--text-muted)", background: "var(--bg-tertiary)", padding: "4px 8px", borderRadius: "12px" }}>
                            Node {exploreState.activeIndex + 1} of {exploreState.traversalNodes.length}
                        </div>
                    </div>
                    {activeNode?.definition && (
                        <p style={{ margin: 0, fontSize: "14px", lineHeight: "1.6", color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                            {activeNode.definition}
                        </p>
                    )}
                </div>

                {/* Sub-filtered Flashcards strictly for this node */}
                <div style={{ flex: 1 }}>
                    <Flashcards 
                        flashcards={activeCards} 
                        onReview={onReview}
                        isEmbedded={true} 
                    />
                </div>

                {/* Traversal Controls */}
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "24px", paddingTop: "16px", borderTop: "1px solid var(--border)" }}>
                    <button 
                        className="btn" 
                        onClick={handlePrevNode} 
                        disabled={exploreState.activeIndex === 0}
                        style={{ opacity: exploreState.activeIndex === 0 ? 0.5 : 1, padding: "8px 16px" }}
                    >
                        ← Previous Concept
                    </button>
                    <button 
                        className="btn btn-primary" 
                        onClick={handleNextNode} 
                        disabled={exploreState.activeIndex === exploreState.traversalNodes.length - 1}
                        style={{ opacity: exploreState.activeIndex === exploreState.traversalNodes.length - 1 ? 0.5 : 1, padding: "8px 16px" }}
                    >
                        Next Concept →
                    </button>
                </div>

            </div>
        </div>
    );
};

export default DeepDive;
