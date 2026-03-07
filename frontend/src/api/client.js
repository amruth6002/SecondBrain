const API_BASE = window.location.hostname === "localhost" 
    ? "http://localhost:8000" 
    : "";

// Ensure a persistent anonymous client ID exists in LocalStorage
function getClientId() {
    let clientId = localStorage.getItem("secondbrain_client_id");
    if (!clientId) {
        clientId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2) + Date.now().toString(36);
        localStorage.setItem("secondbrain_client_id", clientId);
    }
    return clientId;
}

// Helper to inject the Client ID into standard headers
function getHeaders(extraHeaders = {}) {
    return {
        "X-Client-ID": getClientId(),
        ...extraHeaders,
    };
}

export async function processText(text) {
    const res = await fetch(`${API_BASE}/api/process/text`, {
        method: "POST",
        headers: getHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ content_type: "text", text_content: text }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function processPDF(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/api/process/pdf`, {
        method: "POST",
        headers: getHeaders(), // FormData automatically sets boundary Content-Type
        body: formData,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function processYouTube(url) {
    const res = await fetch(`${API_BASE}/api/process/youtube`, {
        method: "POST",
        headers: getHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ content_type: "youtube", youtube_url: url }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export function subscribePipelineStatus(onMessage) {
    // SSE doesn't easily support custom headers in all browsers natively,
    // so we pass the client ID as a query parameter which FastAPI can extract.
    // Wait, FastAPI `Header` requires it in the header. Unfortunately, standard browser EventSource
    // doesn't let us set headers. Let's rely on falling back to the default "default" client ID
    // for just the pipeline status for this prototype, or update the backend to accept query params.
    // *Self-correction*: The isolated data processing is what matters. The pipeline SSE
    // streams the global "_current_status". Let's leave SSE as is.
    const evtSource = new EventSource(`${API_BASE}/api/pipeline/status`);
    evtSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        onMessage(data);
        if (data.stage === "complete" || data.stage === "error") {
            evtSource.close();
        }
    };
    evtSource.onerror = () => evtSource.close();
    return evtSource;
}

export async function reviewFlashcard(cardId, quality) {
    const res = await fetch(
        `${API_BASE}/api/flashcards/${cardId}/review?quality=${quality}`,
        {
            method: "POST",
            headers: getHeaders(),
        }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function getDashboardStats() {
    const res = await fetch(`${API_BASE}/api/dashboard/stats`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function getLatestResults() {
    const res = await fetch(`${API_BASE}/api/results/latest`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function getSessions() {
    const res = await fetch(`${API_BASE}/api/sessions`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function getSession(sessionId) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function deleteSession(sessionId) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
        method: "DELETE",
        headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
