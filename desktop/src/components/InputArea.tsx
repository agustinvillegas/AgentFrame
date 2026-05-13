import React, { useState } from 'react';
import './InputArea.css';
import { Send, AlertCircle } from 'lucide-react';

interface InputAreaProps {
  onSendMessage: (message: string) => void;
  isLoading: boolean;
  error: string | null;
}

const InputArea: React.FC<InputAreaProps> = ({
  onSendMessage,
  isLoading,
  error,
}) => {
  const [input, setInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
      handleSubmit(e as React.FormEvent);
    }
  };

  return (
    <div className="input-area">
      {error && (
        <div className="error-message">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}
      <form onSubmit={handleSubmit} className="input-form">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe what you want the agent to do... (Shift+Enter for newline)"
          disabled={isLoading}
          rows={3}
          maxLength={1000}
        />
        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          className="send-btn"
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
};

export default InputArea;
