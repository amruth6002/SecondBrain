import { useEffect, useRef } from "react";
import Icon from "./Icon";
import AgentCommunicationLog from "./AgentCommunicationLog";

const AGENT_ICON = {
    Planner: "brain",
    Retriever: "search",
    Executor: "bolt",
    System: "pipeline",
};

const AGENT_COLOR = {
    Planner: "#7c83ff",
    Retriever: "#34d399",
    Executor: "#fbbf24",
    System: "#a78bfa",
};

export default function AgentPipeline({ status, variant = "full" }) {
    const feedRef = useRef();
    const messages = status?.agent_messages || [];

    // Auto-scroll to bottom when new messages arrive
    useEffect(() => {
        if (feedRef.current) {
            feedRef.current.scrollTop = feedRef.current.scrollHeight;
        }
    }, [messages.length]);

    const stages = [
        { id: "planner", icon: "brain", label: "Planner", desc: "Creating extraction plan" },
        { id: "retriever", icon: "search", label: "Retriever", desc: "Discovering concepts" },
        { id: "executor", icon: "bolt", label: "Executor", desc: "Generating outputs" },
    ];

    const getStageState = (stageId) => {
        const order = ["idle", "planner", "retriever", "executor", "complete"];
        const ci = order.indexOf(status.stage);
        const si = order.indexOf(stageId);
        if (status.stage === "error") return "error";
        if (ci > si) return "done";
        if (ci === si) return "active";
        return "pending";
    };

    const formatTime = (iso) => {
        try {
            return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        } catch { return ""; }
    };

    const FeedContent = () => (
        <div className="agent-feed agent-feed-standalone">
            <div className="agent-feed-header">
                <Icon name="pipeline" size={14} />
                Agent Communication
                <span className="feed-count">{messages.length}</span>
            </div>
            {messages.length === 0 ? (
                <div className="feed-empty">
                    <Icon name="pipeline" size={28} />
                    <p>Waiting for agents…</p>
                </div>
            ) : (
                <div className="agent-feed-scroll" ref={feedRef}>
                    {messages.map((msg, i) => (
                        <div key={i} className={`feed-message feed-${msg.type || "info"}`}>
                            <div className="feed-agent-badge"
                                style={{
                                    color: AGENT_COLOR[msg.agent] || "#7c83ff",
                                    borderColor: AGENT_COLOR[msg.agent] || "#7c83ff"
                                }}>
                                <Icon name={AGENT_ICON[msg.agent] || "pipeline"} size={11} />
                                {msg.agent}
                            </div>
                            <p className="feed-msg-text">{msg.message}</p>
                            <span className="feed-msg-time">{formatTime(msg.timestamp)}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );

    // Feed-only variant — shown beside the stepper in the split layout
    if (variant === "feed") {
        return (
            <AgentCommunicationLog status={status} />
        );
    }

    // Stepper-only variant — shown on the left in the split layout
    const isStepperOnly = variant === "stepper";

    return (
        <div className={`card ${isStepperOnly ? "" : "pipeline-card"}`}>
            <div className="card-title">
                <Icon name="pipeline" />
                Agent Pipeline
            </div>
            <p className="card-description">
                Three specialized AI agents working in sequence to process your content.
            </p>

            <div className="pipeline-stepper">
                {stages.map((stage) => {
                    const state = getStageState(stage.id);
                    return (
                        <div key={stage.id} className={`pipeline-step ${state}`}>
                            <div className="step-node">
                                <Icon
                                    name={state === "done" ? "check" : state === "error" ? "xmark" : stage.icon}
                                    size={20}
                                />
                            </div>
                            <span className="step-label">{stage.label}</span>
                            <span className="step-desc">{stage.desc}</span>
                        </div>
                    );
                })}
            </div>

            {status.progress > 0 && (
                <div className="progress-section">
                    <div className="progress-meta">
                        <span className="progress-label">Processing</span>
                        <span className="progress-value">{Math.round(status.progress)}%</span>
                    </div>
                    <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${status.progress}%` }} />
                    </div>
                </div>
            )}

            {/* Inline feed only in "full" variant */}
            {!isStepperOnly && messages.length > 0 && <AgentCommunicationLog status={status} />}

            {status.message && (
                <div className="pipeline-status-msg">
                    {status.message}
                </div>
            )}
        </div>
    );
}
