import React, { useState } from 'react';
import './InitialSetup.css';
import { Lock, AlertCircle } from 'lucide-react';

interface InitialSetupProps {
  onInit: (apiKey: string) => void;
  isLoading: boolean;
  error: string | null;
}

const InitialSetup: React.FC<InitialSetupProps> = ({
  onInit,
  isLoading,
  error,
}) => {
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (apiKey.trim()) {
      onInit(apiKey);
    }
  };

  return (
    <div className="initial-setup">
      <div className="setup-container">
        <div className="setup-header">
          <span className="setup-icon">⚙️</span>
          <h1>AgentShell Desktop</h1>
          <p className="subtitle">AI Agent for Windows PC Control</p>
        </div>

        <form onSubmit={handleSubmit} className="setup-form">
          <div className="form-group">
            <label htmlFor="api-key">Anthropic API Key</label>
            <div className="input-wrapper">
              <input
                id="api-key"
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-ant-..."
                disabled={isLoading}
                required
              />
              <button
                type="button"
                className="toggle-btn"
                onClick={() => setShowKey(!showKey)}
                disabled={isLoading}
              >
                {showKey ? '🙈' : '👁️'}
              </button>
            </div>
            <p className="help-text">
              You can get your API key from{' '}
              <a
                href="https://console.anthropic.com"
                target="_blank"
                rel="noopener noreferrer"
              >
                console.anthropic.com
              </a>
            </p>
          </div>

          {error && (
            <div className="error-box-setup">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={!apiKey.trim() || isLoading}
            className="submit-btn"
          >
            {isLoading ? (
              <>
                <span className="spinner"></span>
                Initializing...
              </>
            ) : (
              <>
                <Lock size={18} />
                Start Agent
              </>
            )}
          </button>
        </form>

        <div className="setup-footer">
          <p>Your API key is only used locally and never stored.</p>
        </div>
      </div>
    </div>
  );
};

export default InitialSetup;
