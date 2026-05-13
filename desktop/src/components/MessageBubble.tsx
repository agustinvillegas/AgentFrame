import React, { useState } from 'react';
import './MessageBubble.css';
import { Copy, ChevronDown, ChevronUp } from 'lucide-react';

interface MessageProps {
  message: {
    id: string;
    role: 'user' | 'agent';
    content: string;
    timestamp: Date;
    command?: string;
    result?: any;
    error?: string;
  };
}

const MessageBubble: React.FC<MessageProps> = ({ message }) => {
  const [expandedCommand, setExpandedCommand] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatJson = (obj: any) => {
    return JSON.stringify(obj, null, 2);
  };

  return (
    <div className={`message-bubble ${message.role}`}>
      <div className={`message-header ${message.role}`}>
        <span className="sender">
          {message.role === 'user' ? '👤 You' : '🤖 Agent'}
        </span>
        <span className="time">
          {message.timestamp.toLocaleTimeString('es-ES', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      </div>

      <div className="message-content">
        <p>{message.content}</p>

        {message.error && (
          <div className="error-box">
            <strong>Error:</strong> {message.error}
          </div>
        )}

        {message.command && (
          <div className="command-box">
            <div className="command-header">
              <span className="command-label">
                <code>$</code> Command
              </span>
              <button
                className="copy-btn"
                onClick={() => handleCopy(message.command!)}
                title={copied ? 'Copied!' : 'Copy command'}
              >
                <Copy size={16} />
              </button>
            </div>
            <pre className="command-text">{message.command}</pre>
          </div>
        )}

        {message.result && (
          <div className="result-box">
            <button
              className="result-toggle"
              onClick={() => setExpandedCommand(!expandedCommand)}
            >
              {expandedCommand ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              <span>Result</span>
              {message.result.ok !== undefined && (
                <span className={`status ${message.result.ok ? 'ok' : 'error'}`}>
                  {message.result.ok ? '✓ OK' : '✗ FAILED'}
                </span>
              )}
            </button>

            {expandedCommand && (
              <pre className="result-text">
                {formatJson(message.result)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
