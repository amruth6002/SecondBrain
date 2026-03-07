import { useState, useRef } from "react";
import Icon from "./Icon";

export default function Upload({ onProcess, isProcessing }) {
    const [mode, setMode] = useState("text");
    const [text, setText] = useState("");
    const [youtubeUrl, setYoutubeUrl] = useState("");
    const [fileName, setFileName] = useState("");
    const fileRef = useRef(null);

    const handleSubmit = () => {
        if (mode === "text" && text.trim()) {
            onProcess({ type: "text", data: text });
            setText("");
        } else if (mode === "youtube" && youtubeUrl.trim()) {
            onProcess({ type: "youtube", data: youtubeUrl });
        } else if (mode === "pdf" && fileRef.current?.files[0]) {
            onProcess({ type: "pdf", data: fileRef.current.files[0] });
        }
    };

    const tabs = [
        { id: "text", icon: "text", label: "Text" },
        { id: "pdf", icon: "pdf", label: "PDF" },
        { id: "youtube", icon: "youtube", label: "YouTube" },
    ];

    return (
        <div className="card upload-card">
            <div className="card-title">
                <Icon name="cloud_upload" />
                Upload Content
            </div>
            <p className="card-description">
                Paste text, upload a PDF, or provide a YouTube link to extract knowledge.
            </p>

            <div className="tab-bar">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        className={`tab ${mode === tab.id ? "active" : ""}`}
                        onClick={() => setMode(tab.id)}
                    >
                        <Icon name={tab.icon} size={15} />
                        {tab.label}
                    </button>
                ))}
            </div>

            <div className="input-area">
                {mode === "text" && (
                    <>
                        <textarea
                            placeholder="Paste your notes, lecture content, or study material here..."
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            rows={8}
                        />
                        {text.length > 0 && (
                            <p className="char-counter">
                                {text.length.toLocaleString()} chars
                                &nbsp;·&nbsp;
                                {text.trim().split(/\s+/).filter(Boolean).length.toLocaleString()} words
                            </p>
                        )}
                    </>
                )}
                {mode === "pdf" && (
                    <div className="file-upload">
                        <input
                            type="file"
                            accept=".pdf"
                            ref={fileRef}
                            onChange={(e) => setFileName(e.target.files[0]?.name || "")}
                            id="pdf-input"
                        />
                        <label htmlFor="pdf-input" className="file-label">
                            <Icon name="cloud_upload" size={32} />
                            {fileName ? (
                                <span className="file-name">{fileName}</span>
                            ) : (
                                "Drop a PDF here or click to browse"
                            )}
                        </label>
                    </div>
                )}
                {mode === "youtube" && (
                    <input
                        type="text"
                        placeholder="https://www.youtube.com/watch?v=..."
                        value={youtubeUrl}
                        onChange={(e) => setYoutubeUrl(e.target.value)}
                        className="url-input"
                    />
                )}
            </div>

            <button
                className="btn-primary"
                onClick={handleSubmit}
                disabled={isProcessing}
            >
                {isProcessing ? (
                    <span className="processing-spinner">
                        <Icon name="loader" size={16} className="spin" />
                        Processing...
                    </span>
                ) : (
                    <>
                        <Icon name="play" size={16} />
                        Process with SecondBrain
                    </>
                )}
            </button>
        </div>
    );
}
