import React, { useState, useRef, useEffect } from "react";
import Icon from "./Icon";
import { askChatbot } from "../api/client";

export default function Chatbot({ notebookId = null }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! Ask me anything about your SecondBrain knowledge base." }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) scrollToBottom();
  }, [messages, isOpen]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg = input.trim();
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await askChatbot(userMsg, notebookId);
      
      let sourceStr = "";
      if (res.sources && res.sources.length > 0) {
        const uniqueSources = Array.from(new Set(res.sources.map(s => s.name)));
        sourceStr = "\n\n**Sources:** " + uniqueSources.join(", ");
      }
      
      setMessages(prev => [...prev, { 
        role: "assistant", 
        content: res.answer + sourceStr
      }]);
    } catch (err) {
      setMessages(prev => [...prev, { 
        role: "assistant", 
        content: "Sorry, I encountered an error connecting to your SecondBrain." 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chatbot-widget">
      {isOpen ? (
        <div className="chatbot-window card fade-in">
          <div className="chatbot-header">
            <div>
              <h3>Ask SecondBrain</h3>
              <span className="chatbot-subtitle">{notebookId ? "Searching current notebook" : "Searching all knowledge"}</span>
            </div>
            <button onClick={() => setIsOpen(false)} className="chatbot-close-btn" title="Close chat">
              <Icon name="xmark" size={16} />
            </button>
          </div>
          
          <div className="chatbot-messages">
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role}`}>
                {m.content.split('\n').map((line, j) => (
                  <p key={j}>{line}</p>
                ))}
              </div>
            ))}
            {isLoading && (
              <div className="chat-bubble assistant loading">
                <span className="dot"></span><span className="dot"></span><span className="dot"></span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSubmit} className="chatbot-input-area">
            <input
              type="text"
              placeholder="Ask a question..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isLoading}
            />
            <button type="submit" disabled={!input.trim() || isLoading} className="btn btn-primary">
              <Icon name="sparkles" size={14} />
            </button>
          </form>
        </div>
      ) : (
        <button className="chatbot-fab bounce-in" onClick={() => setIsOpen(true)} title="Ask SecondBrain">
          <Icon name="sparkles" size={24} />
        </button>
      )}
    </div>
  );
}
