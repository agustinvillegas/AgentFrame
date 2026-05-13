import React from 'react';
import './Header.css';
import { Menu, RotateCcw, Settings } from 'lucide-react';

interface HeaderProps {
  onToggleCommandPanel: () => void;
  onClearChat: () => void;
}

const Header: React.FC<HeaderProps> = ({ onToggleCommandPanel, onClearChat }) => {
  return (
    <header className="header">
      <div className="header-left">
        <div className="logo">
          <span className="logo-icon">⚙️</span>
          <h1>AgentShell</h1>
        </div>
      </div>

      <div className="header-center">
        <p className="status">Ready to control your PC</p>
      </div>

      <div className="header-right">
        <button
          className="header-btn"
          onClick={onToggleCommandPanel}
          title="Toggle Command Panel"
        >
          <Menu size={20} />
        </button>
        <button
          className="header-btn"
          onClick={onClearChat}
          title="Clear Chat History"
        >
          <RotateCcw size={20} />
        </button>
        <button
          className="header-btn settings"
          title="Settings"
        >
          <Settings size={20} />
        </button>
      </div>
    </header>
  );
};

export default Header;
