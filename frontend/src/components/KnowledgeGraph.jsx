import { useRef, useEffect, useCallback, useState, useMemo } from "react";
import ForceGraph2D from "react-force-graph-2d";
import Icon from "./Icon";

// Constants outside component to avoid stale closure issues
const CATEGORY_COLORS = {
    definition: "#7c83ff",
    theorem: "#fb7185",
    process: "#34d399",
    formula: "#fbbf24",
    example: "#a78bfa",
    principle: "#22d3ee",
    default: "#7c83ff",
};

const IMPORTANCE_SIZE = {
    high: 10,
    medium: 7,
    low: 5,
};

export default function KnowledgeGraph({ nodes, edges }) {
    const graphRef = useRef();
    const containerRef = useRef();
    const [dimensions, setDimensions] = useState({ width: 500, height: 340 });
    const [selectedNode, setSelectedNode] = useState(null);
    const [isExpanded, setIsExpanded] = useState(false);
    const [isCollapsed, setIsCollapsed] = useState(false);

    // Memoize graph data — prevents ForceGraph from resetting simulation on every render
    const graphData = useMemo(() => {
        // Spread nodes out initially to prevent infinite repulsion physics (NaN explosion)
        const spreadNodes = nodes.map((n) => ({
            id: n.id || n.label, // Fallback to label if LLM omitted ID
            label: n.label,
            category: n.category,
            importance: n.importance,
            definition: n.definition || "",
            /* eslint-disable react-hooks/purity */
            x: (Math.random() - 0.5) * 100, // Intentional Jitter
            y: (Math.random() - 0.5) * 100, // Intentional Jitter
            /* eslint-enable react-hooks/purity */
        }));

        // Build a robust lookup catalog to map LLM edge targets back to strict node IDs
        const nodeDirectory = {};
        spreadNodes.forEach(n => {
            nodeDirectory[n.id] = n.id;
            if (n.label) {
                nodeDirectory[n.label] = n.id;
                nodeDirectory[n.label.toLowerCase().trim()] = n.id;
            }
        });

        // Resolve edge connections to guarantee they point to existing node IDs
        const validLinks = edges
            .map(e => {
                const rawSrc = String(e.source || "").trim();
                const rawTgt = String(e.target || "").trim();

                let srcId = nodeDirectory[rawSrc] || nodeDirectory[rawSrc.toLowerCase()];
                let tgtId = nodeDirectory[rawTgt] || nodeDirectory[rawTgt.toLowerCase()];

                // Fuzzy fallback if the LLM hallucinated the structural name (e.g. omitting "(JVM)")
                if (!srcId && rawSrc) {
                    const fuzzy = spreadNodes.find(n => n.label.toLowerCase().includes(rawSrc.toLowerCase()) || rawSrc.toLowerCase().includes(n.label.toLowerCase()));
                    if (fuzzy) srcId = fuzzy.id;
                }
                if (!tgtId && rawTgt) {
                    const fuzzy = spreadNodes.find(n => n.label.toLowerCase().includes(rawTgt.toLowerCase()) || rawTgt.toLowerCase().includes(n.label.toLowerCase()));
                    if (fuzzy) tgtId = fuzzy.id;
                }

                return {
                    source: srcId,
                    target: tgtId,
                    label: e.label,
                    strength: e.strength
                };
            })
            // CRITICAL: Drop any edges that couldn't be resolved. This PREVENTS the physics crash.
            .filter(e => e.source && e.target);

        return {
            nodes: spreadNodes,
            links: validLinks,
        };
    }, [nodes, edges]);

    const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        const LIGHT_COLORS = {
            definition: "#4338ca", theorem: "#e11d48", process: "#059669", 
            formula: "#d97706", example: "#7e22ce", principle: "#0891b2", default: "#4338ca"
        };
        
        const label = node.label || "";
        const fontSize = Math.max(11 / globalScale, 3);
        const size = IMPORTANCE_SIZE[node.importance] || 7;
        
        const activeColors = isLight ? LIGHT_COLORS : CATEGORY_COLORS;
        const color = activeColors[node.category] || activeColors.default;

        // Outer glow
        ctx.shadowColor = color;
        ctx.shadowBlur = isLight ? 10 : 20;

        // Node circle
        ctx.beginPath();
        ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();

        ctx.shadowBlur = 0;

        // Subtle ring
        ctx.strokeStyle = isLight ? "rgba(0,0,0,0.1)" : "rgba(124,131,255,0.4)";
        ctx.lineWidth = 0.5;
        ctx.stroke();

        // Label
        ctx.font = `500 ${fontSize}px Inter, sans-serif`;
        ctx.fillStyle = isLight ? "#0f172a" : "#f0f0f3";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillText(label, node.x, node.y + size + 3);
    }, []);

    // Responsive container sizing
    useEffect(() => {
        const updateSize = () => {
            if (containerRef.current) {
                const rect = containerRef.current.getBoundingClientRect();
                const newWidth = Math.floor(rect.width) - 48;
                // Subtract approximate header/footer padding from container height
                const newHeight = Math.max(300, Math.floor(rect.height) - 150);
                setDimensions(prev => {
                    if (Math.abs(prev.width - newWidth) > 5 || Math.abs(prev.height - newHeight) > 5) {
                        return { width: newWidth, height: newHeight };
                    }
                    return prev;
                });
            }
        };
        updateSize();
        const resizeObserver = new ResizeObserver(updateSize);
        if (containerRef.current) resizeObserver.observe(containerRef.current);
        return () => resizeObserver.disconnect();
    }, []);

    // Handle initial physics tuning and camera fit robustly
    useEffect(() => {
        if (graphRef.current && nodes.length > 0) {
            // Stronger repulsion to prevent clustered nodes, restricted distance to prevent them flying off canvas
            graphRef.current.d3Force("charge").strength(-300).distanceMax(250);

            // Re-warm physics slightly on data change
            graphRef.current.d3ReheatSimulation();

            // Fit camera to view once the graph has had a fraction of a second to organically expand
            const timer = setTimeout(() => {
                if (graphRef.current) {
                    graphRef.current.zoomToFit(400, 40);
                }
            }, 600);

            return () => clearTimeout(timer);
        }
    }, [nodes]);

    const handleZoomIn = () => graphRef.current?.zoom(1.5, 300);
    const handleZoomOut = () => graphRef.current?.zoom(0.67, 300);
    const handleFit = () => graphRef.current?.zoomToFit(400, 50);

    const handleExpandToggle = () => {
        setIsExpanded(prev => {
            const next = !prev;
            if (next) {
                document.body.classList.add("has-expanded-modal");
            } else {
                document.body.classList.remove("has-expanded-modal");
            }
            // Re-fit camera after CSS transition completes
            setTimeout(() => {
                if (graphRef.current) graphRef.current.zoomToFit(400, 40);
            }, 300);
            return next;
        });
    };

    if (!nodes.length) {
        return (
            <div className="card graph-card">
                <div className="card-title">
                    <Icon name="graph" />
                    Knowledge Graph
                </div>
                <div className="empty-state">
                    <Icon name="graph" size={48} className="empty-icon" />
                    <p>Process content to see your knowledge graph</p>
                </div>
            </div>
        );
    }

    return (
        <>
            {isExpanded && <div className="graph-modal-backdrop" onClick={handleExpandToggle} />}
            <div className={`card graph-card ${isExpanded ? "graph-card-expanded" : ""}`} ref={containerRef}>
                <div className="card-title">
                    <Icon name="graph" />
                    Knowledge Graph
                    {!isExpanded && (
                        <button className="collapse-btn" onClick={() => setIsCollapsed(!isCollapsed)} title="Toggle collapse">
                            <Icon name={isCollapsed ? "chevron_down" : "chevron_up"} size={16} />
                        </button>
                    )}
                </div>

                {!isCollapsed && (
                    <>
                        <div className="graph-stats">
                            <span className="graph-stat">
                                <strong>{nodes.length}</strong> concepts
                            </span>
                            <span className="graph-stat">
                                <strong>{edges.length}</strong> connections
                            </span>
                        </div>

                        <div className="graph-wrapper">
                            <div className="graph-controls">
                                <button className="graph-control-btn" onClick={handleZoomIn} title="Zoom in"><Icon name="zoom_in" size={14} /></button>
                                <button className="graph-control-btn" onClick={handleZoomOut} title="Zoom out"><Icon name="zoom_out" size={14} /></button>
                                <button className="graph-control-btn" onClick={handleFit} title="Fit to view"><Icon name="fit" size={14} /></button>
                                <button className="graph-control-btn" onClick={handleExpandToggle} title={isExpanded ? "Minimize" : "Expand Fullscreen"}>
                                    <Icon name={isExpanded ? "arrows_in" : "arrows_out"} size={14} />
                                </button>
                            </div>
                            <ForceGraph2D
                                ref={graphRef}
                                graphData={graphData}
                                nodeCanvasObject={nodeCanvasObject}
                                nodeCanvasObjectMode={() => "replace"}
                                onNodeClick={(node) => setSelectedNode(node)}
                                linkColor={() => "rgba(124, 131, 255, 0.3)"}
                                linkWidth={(link) => (link.strength || 0.5) * 2.5}
                                linkDirectionalParticles={2}
                                linkDirectionalParticleWidth={1.5}
                                linkDirectionalParticleColor={() => "#7c83ff"}
                                backgroundColor="transparent"
                                width={dimensions.width}
                                height={dimensions.height}
                                cooldownTicks={100}
                            />
                        </div>

                        {/* Node Detail Panel */}
                        {selectedNode && (() => {
                            const connected = edges
                                .filter(e => e.source === selectedNode.id || e.target === selectedNode.id)
                                .map(e => ({
                                    label: e.source === selectedNode.id ? e.target : e.source,
                                    rel: e.label,
                                }));
                            const color = CATEGORY_COLORS[selectedNode.category] || CATEGORY_COLORS.default;
                            return (
                                <div className="node-panel">
                                    <button className="node-panel-close" onClick={() => setSelectedNode(null)}>
                                        <Icon name="xmark" size={14} />
                                    </button>
                                    <div className="node-panel-header">
                                        <span className="node-panel-dot" style={{ background: color }} />
                                        <strong className="node-panel-name">{selectedNode.label}</strong>
                                    </div>
                                    <div className="node-panel-meta">
                                        <span className="node-panel-badge" style={{ color, borderColor: color }}>
                                            {selectedNode.category}
                                        </span>
                                        <span className="node-panel-badge" style={{ color: "#a78bfa", borderColor: "#a78bfa" }}>
                                            {selectedNode.importance} importance
                                        </span>
                                    </div>
                                    {selectedNode.definition && (
                                        <p className="node-panel-definition">{selectedNode.definition}</p>
                                    )}
                                    {connected.length > 0 && (
                                        <div className="node-panel-connections">
                                            <p className="node-panel-section-label">Connected to</p>
                                            {connected.map((c, i) => (
                                                <div key={i} className="node-connection-item">
                                                    <span className="node-connection-rel">{c.rel}</span>
                                                    <span className="node-connection-target">{c.label}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            );
                        })()}

                        <div className="graph-legend">
                            {Object.entries(CATEGORY_COLORS)
                                .filter(([k]) => k !== "default")
                                .map(([cat, color]) => (
                                    <span key={cat} className="legend-item">
                                        <span className="legend-dot" style={{ background: color }} />
                                        {cat}
                                    </span>
                                ))}
                        </div>
                    </>
                )}
            </div>
        </>
    );
}
