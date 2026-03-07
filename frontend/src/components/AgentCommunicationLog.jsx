import React, { useEffect, useRef } from "react";

export default function AgentCommunicationLog({ status }) {
    const bottomRef = useRef(null);

    // Auto-scroll to the bottom when new logs arrive
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [status?.agent_messages]);

    if (!status || !status.agent_messages || status.agent_messages.length === 0) {
        return null;
    }

    // Assign consistent colors based on the sender agent
    const getAgentColor = (agent) => {
        switch (agent.toLowerCase()) {
            case "planner": return "var(--accent)";
            case "retriever": return "var(--success)";
            case "executor": return "var(--warning)";
            case "userproxy": return "var(--accent-light)";
            case "system": return "var(--text-muted)";
            default: return "var(--text-secondary)";
        }
    };

    return (
        <div className="agent-log-container card">
            <div className="agent-log-header">
                <h3>📡 Live Agent Wiretap</h3>
                <div className="recording-indicator">
                    <span className="pulse-dot-red"></span> Intercepting
                </div>
            </div>

            <div className="agent-log-window">
                {status.agent_messages.map((log, index) => (
                    <div key={index} className="log-entry">
                        <div className="log-meta">
                            <span className="log-time">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                            <span className="log-route" style={{ color: getAgentColor(log.agent) }}>
                                {log.agent} {log.receiver && `➔ ${log.receiver}`}
                            </span>
                        </div>
                        {log.action && log.action !== "LOG" && (
                            <div className="log-action">{log.action}</div>
                        )}
                        <pre className="log-content" style={{
                            color: log.type === "error" ? "var(--error)" :
                                log.type === "thinking" ? "var(--text-muted)" : "var(--success)"
                        }}>
                            {/* Typewriter CSS effect implemented via standard slideIn animation inherited from index.css */}
                            {log.message}
                        </pre>
                    </div>
                ))}
                <div ref={bottomRef} />
            </div>
        </div>
    );
}
