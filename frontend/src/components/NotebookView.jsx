import { useState, useEffect, useCallback, useRef } from "react";
import Icon from "./Icon";
import KnowledgeGraph from "./KnowledgeGraph";
import Flashcards from "./Flashcards";
import Concepts from "./Concepts";
import AgentPipeline from "./AgentPipeline";
import {
    getNotebook, addTextBlock, addPDFBlock, addYouTubeBlock,
    deleteBlock, processNotebook, subscribePipelineStatus,
    renameNotebook, getNotebookProcessingStatus,
} from "../api/client";

export default function NotebookView({ notebookId, onToast, onRefresh }) {
    const [notebook, setNotebook] = useState(null);
    const [loading, setLoading] = useState(true);
    const [addingBlock, setAddingBlock] = useState(null); // null | "text" | "pdf" | "youtube"
    const [isProcessing, setIsProcessing] = useState(false);
    const [pipelineStatus, setPipelineStatus] = useState({ stage: "idle", progress: 0, message: "" });
    const [activeTab, setActiveTab] = useState("blocks");
    const [editingName, setEditingName] = useState(false);
    const [nameInput, setNameInput] = useState("");

    // Block input state
    const [textInput, setTextInput] = useState("");
    const [textTitle, setTextTitle] = useState("");
    const [youtubeUrl, setYoutubeUrl] = useState("");
    const [pdfFile, setPdfFile] = useState(null);
    const sseRef = useRef(null);
    const [expandedBlocks, setExpandedBlocks] = useState({});

    const fetchNotebook = useCallback(async () => {
        try {
            setLoading(true);
            const nb = await getNotebook(notebookId);
            setNotebook(nb);
            setNameInput(nb.name);
        } catch {
            onToast?.("Failed to load notebook", "error");
        } finally {
            setLoading(false);
        }
    }, [notebookId, onToast]);

    useEffect(() => {
        fetchNotebook();
        setActiveTab("blocks");
        setAddingBlock(null);

        // Check if this notebook is already being processed (e.g. after navigation or refresh)
        let cancelled = false;
        (async () => {
            try {
                const status = await getNotebookProcessingStatus(notebookId);
                if (cancelled) return;
                if (status.processing) {
                    setIsProcessing(true);
                    setPipelineStatus({ stage: status.stage, progress: status.progress, message: status.message });
                    // Re-subscribe to SSE to continue tracking
                    connectSSE();
                } else {
                    setIsProcessing(false);
                }
            } catch {
                if (!cancelled) setIsProcessing(false);
            }
        })();

        return () => {
            cancelled = true;
            // Close any open SSE connection when leaving
            if (sseRef.current) {
                sseRef.current.close();
                sseRef.current = null;
            }
        };
    }, [fetchNotebook, notebookId]); // eslint-disable-line react-hooks/exhaustive-deps

    const connectSSE = useCallback(() => {
        // Close existing connection if any
        if (sseRef.current) {
            sseRef.current.close();
            sseRef.current = null;
        }
        const es = subscribePipelineStatus((status) => {
            setPipelineStatus(status);
            if (status.stage === "complete") {
                setIsProcessing(false);
                sseRef.current = null;
                fetchNotebook();
                setActiveTab("concepts");
                onToast?.("Processing complete!", "success");
                onRefresh?.();
            } else if (status.stage === "error") {
                setIsProcessing(false);
                sseRef.current = null;
                onToast?.(status.message || "Processing failed", "error");
            }
        });
        sseRef.current = es;
    }, [fetchNotebook, onToast, onRefresh]);

    const handleRename = async () => {
        if (!nameInput.trim() || nameInput === notebook?.name) {
            setEditingName(false);
            return;
        }
        try {
            await renameNotebook(notebookId, nameInput);
            setNotebook(prev => ({ ...prev, name: nameInput }));
            setEditingName(false);
            onRefresh?.();
        } catch {
            onToast?.("Failed to rename", "error");
        }
    };

    const handleAddTextBlock = async () => {
        if (!textInput.trim()) return;
        try {
            await addTextBlock(notebookId, textTitle || "Text notes", textInput);
            setTextInput(""); setTextTitle(""); setAddingBlock(null);
            fetchNotebook();
            onToast?.("Block added", "success");
        } catch { onToast?.("Failed to add block", "error"); }
    };

    const handleAddPDFBlock = async () => {
        if (!pdfFile) return;
        try {
            await addPDFBlock(notebookId, pdfFile);
            setPdfFile(null); setAddingBlock(null);
            fetchNotebook();
            onToast?.("PDF block added", "success");
        } catch { onToast?.("Failed to add PDF", "error"); }
    };

    const handleAddYouTubeBlock = async () => {
        if (!youtubeUrl.trim()) return;
        try {
            await addYouTubeBlock(notebookId, youtubeUrl);
            setYoutubeUrl(""); setAddingBlock(null);
            fetchNotebook();
            onToast?.("YouTube block added", "success");
        } catch (e) { onToast?.(e.message || "Failed to add YouTube", "error"); }
    };

    const handleDeleteBlock = async (blockId) => {
        try {
            await deleteBlock(blockId);
            fetchNotebook();
            onToast?.("Block removed", "success");
        } catch { onToast?.("Failed to delete block", "error"); }
    };

    const handleProcess = async () => {
        if (!notebook?.blocks?.length) {
            onToast?.("Add some content blocks first", "error");
            return;
        }
        setIsProcessing(true);
        setPipelineStatus({ stage: "planner", progress: 5, message: "Starting..." });
        try {
            await processNotebook(notebookId);
        } catch (e) {
            onToast?.(e.message || "Failed to start processing", "error");
            setIsProcessing(false);
            return;
        }
        connectSSE();
    };

    if (loading) {
        return (
            <div className="card">
                <div className="empty-state">
                    <Icon name="loader" size={32} className="spin" />
                    <p>Loading notebook...</p>
                </div>
            </div>
        );
    }

    if (!notebook) {
        return (
            <div className="card">
                <div className="empty-state">
                    <Icon name="exclamation" size={48} className="empty-icon" />
                    <p>Notebook not found</p>
                </div>
            </div>
        );
    }

    const hasResults = (notebook.concepts?.length > 0) || (notebook.flashcards?.length > 0);

    const BLOCK_ICONS = { pdf: "pdf", youtube: "youtube", text: "text" };

    const toggleBlockExpand = (id) => {
        setExpandedBlocks(prev => ({ ...prev, [id]: !prev[id] }));
    };

    return (
        <div className="notebook-view">
            {/* Notebook Header */}
            <div className="notebook-header">
                <div className="notebook-title-area">
                    {editingName ? (
                        <input
                            className="notebook-name-input"
                            value={nameInput}
                            onChange={(e) => setNameInput(e.target.value)}
                            onBlur={handleRename}
                            onKeyDown={(e) => e.key === "Enter" && handleRename()}
                            autoFocus
                        />
                    ) : (
                        <h2 className="notebook-name" onClick={() => setEditingName(true)} title="Click to rename">
                            <Icon name="book" size={20} />
                            {notebook.name}
                            <Icon name="text" size={12} className="edit-hint" />
                        </h2>
                    )}
                    <span className="notebook-meta">
                        {notebook.blocks?.length || 0} blocks
                        {hasResults && ` · ${notebook.concepts?.length || 0} concepts · ${notebook.flashcards?.length || 0} cards`}
                    </span>
                </div>
                {!isProcessing ? (
                    <button
                        className="btn btn-primary"
                        onClick={handleProcess}
                        disabled={!notebook.blocks?.length}
                    >
                        <Icon name="pipeline" size={16} />
                        Process with AI
                    </button>
                ) : (
                    <button className="btn" disabled style={{ opacity: 0.8 }}>
                        <Icon name="loader" size={16} className="spin" />
                        Processing...
                    </button>
                )}
            </div>

            {/* Pipeline Processing Area */}
            {isProcessing && (
                <div className="notebook-processing" style={{ marginTop: "1rem", marginBottom: "2rem", padding: "1.5rem", background: "var(--bg-elevated)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}>
                    <div className="pipeline-split">
                        <AgentPipeline status={pipelineStatus} variant="stepper" />
                        <AgentPipeline status={pipelineStatus} variant="feed" />
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="notebook-tabs">
                <button className={`tab-btn ${activeTab === "blocks" ? "active" : ""}`} onClick={() => setActiveTab("blocks")}>
                    <Icon name="text" size={14} /> Content
                    <span className="tab-count">{notebook.blocks?.length || 0}</span>
                </button>
                {hasResults && (
                    <>
                        <button className={`tab-btn ${activeTab === "concepts" ? "active" : ""}`} onClick={() => setActiveTab("concepts")}>
                            <Icon name="book" size={14} /> Concepts
                            <span className="tab-count">{notebook.concepts?.length || 0}</span>
                        </button>
                        <button className={`tab-btn ${activeTab === "flashcards" ? "active" : ""}`} onClick={() => setActiveTab("flashcards")}>
                            <Icon name="cards" size={14} /> Flashcards
                            <span className="tab-count">{notebook.flashcards?.length || 0}</span>
                        </button>
                        <button className={`tab-btn ${activeTab === "graph" ? "active" : ""}`} onClick={() => setActiveTab("graph")}>
                            <Icon name="graph" size={14} /> Graph
                        </button>
                    </>
                )}
            </div>

            {/* Blocks Tab */}
            {activeTab === "blocks" && (
                <div className="blocks-section">
                    {/* Overlap info banner */}
                    {notebook.overlap?.overlapping_concepts?.length > 0 && (
                        <div className="overlap-banner">
                            <Icon name="brain" size={16} />
                            <div>
                                <strong>You already know:</strong>{" "}
                                {notebook.overlap.overlapping_concepts.join(", ")}
                                {notebook.overlap.new_concepts?.length > 0 && (
                                    <span className="new-concepts-note">
                                        {" · "}{notebook.overlap.new_concepts.length} new concepts learned
                                    </span>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Block list */}
                    {notebook.blocks?.length === 0 ? (
                        <div className="card">
                            <div className="empty-state">
                                <Icon name="upload" size={48} className="empty-icon" />
                                <p>No content yet. Add text, PDFs, or YouTube videos below.</p>
                            </div>
                        </div>
                    ) : (
                        <div className="blocks-list">
                            {notebook.blocks.map((block) => (
                                <div key={block.id} className="block-card">
                                    <div className="block-card-icon">
                                        <Icon name={BLOCK_ICONS[block.block_type] || "text"} size={20} />
                                    </div>
                                    <div className="block-card-content">
                                        <h4 className="block-title">
                                            {block.title || block.block_type.toUpperCase()}
                                            <span className="block-badge">{block.block_type}</span>
                                        </h4>
                                        <p className="block-preview" style={{ whiteSpace: "pre-wrap", color: "var(--text-secondary)", fontSize: "0.85rem", lineHeight: "1.5", marginTop: "0.5rem" }}>
                                            {expandedBlocks[block.id]
                                                ? block.content
                                                : `${block.content?.slice(0, 300)}${block.content?.length > 300 ? "…" : ""}`
                                            }
                                            {block.content?.length > 300 && (
                                                <button
                                                    onClick={() => toggleBlockExpand(block.id)}
                                                    style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', marginLeft: '0.5rem', padding: 0 }}
                                                >
                                                    {expandedBlocks[block.id] ? "Show less" : "Show more"}
                                                </button>
                                            )}
                                        </p>
                                        <div className="block-meta">
                                            <span>{block.content ? `${block.content.length.toLocaleString()} chars` : "Empty"}</span>
                                            {block.created_at && <span>{new Date(block.created_at).toLocaleDateString()}</span>}
                                        </div>
                                    </div>
                                    <button className="block-delete-btn" onClick={() => handleDeleteBlock(block.id)} title="Remove block">
                                        <Icon name="xmark" size={14} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Add Block */}
                    <div className="add-block-area">
                        {!addingBlock ? (
                            <div className="add-block-buttons">
                                <button className="add-block-btn" onClick={() => setAddingBlock("text")}>
                                    <Icon name="text" size={16} /> Add Text
                                </button>
                                <button className="add-block-btn" onClick={() => setAddingBlock("pdf")}>
                                    <Icon name="pdf" size={16} /> Add PDF
                                </button>
                                <button className="add-block-btn" onClick={() => setAddingBlock("youtube")}>
                                    <Icon name="youtube" size={16} /> Add YouTube
                                </button>
                            </div>
                        ) : addingBlock === "text" ? (
                            <div className="add-block-form card">
                                <div className="add-block-form-header">
                                    <Icon name="text" size={16} />
                                    <span>Add Text Block</span>
                                    <button className="close-btn" onClick={() => setAddingBlock(null)}><Icon name="xmark" size={14} /></button>
                                </div>
                                <input
                                    className="input-field"
                                    placeholder="Title (optional)"
                                    value={textTitle}
                                    onChange={(e) => setTextTitle(e.target.value)}
                                />
                                <textarea
                                    className="textarea-field"
                                    placeholder="Paste your notes, text content, or study material here..."
                                    value={textInput}
                                    onChange={(e) => setTextInput(e.target.value)}
                                    rows={6}
                                />
                                <button className="btn btn-primary" onClick={handleAddTextBlock} disabled={!textInput.trim()}>
                                    <Icon name="check" size={14} /> Add Block
                                </button>
                            </div>
                        ) : addingBlock === "pdf" ? (
                            <div className="add-block-form card">
                                <div className="add-block-form-header">
                                    <Icon name="pdf" size={16} />
                                    <span>Add PDF Block</span>
                                    <button className="close-btn" onClick={() => setAddingBlock(null)}><Icon name="xmark" size={14} /></button>
                                </div>
                                <div className="file-upload-zone" onClick={() => document.getElementById('nb-pdf-input').click()}>
                                    <Icon name="cloud_upload" size={32} />
                                    <p>{pdfFile ? pdfFile.name : "Click to select a PDF file"}</p>
                                    <input id="nb-pdf-input" type="file" accept=".pdf" hidden onChange={(e) => setPdfFile(e.target.files[0])} />
                                </div>
                                <button className="btn btn-primary" onClick={handleAddPDFBlock} disabled={!pdfFile}>
                                    <Icon name="check" size={14} /> Add Block
                                </button>
                            </div>
                        ) : addingBlock === "youtube" ? (
                            <div className="add-block-form card">
                                <div className="add-block-form-header">
                                    <Icon name="youtube" size={16} />
                                    <span>Add YouTube Block</span>
                                    <button className="close-btn" onClick={() => setAddingBlock(null)}><Icon name="xmark" size={14} /></button>
                                </div>
                                <input
                                    className="input-field"
                                    placeholder="https://www.youtube.com/watch?v=..."
                                    value={youtubeUrl}
                                    onChange={(e) => setYoutubeUrl(e.target.value)}
                                />
                                <button className="btn btn-primary" onClick={handleAddYouTubeBlock} disabled={!youtubeUrl.trim()}>
                                    <Icon name="check" size={14} /> Add Block
                                </button>
                            </div>
                        ) : null}
                    </div>
                </div>
            )}

            {/* Concepts Tab */}
            {activeTab === "concepts" && hasResults && (
                <Concepts concepts={notebook.concepts || []} />
            )}

            {/* Flashcards Tab */}
            {activeTab === "flashcards" && hasResults && (
                <Flashcards flashcards={notebook.flashcards || []} onToast={onToast} />
            )}

            {/* Graph Tab */}
            {activeTab === "graph" && hasResults && (
                <KnowledgeGraph nodes={notebook.graph_nodes || []} edges={notebook.graph_edges || []} />
            )}
        </div>
    );
}
