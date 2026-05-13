import  { forwardRef } from 'react';
import './ChatArea.css';
import MessageBubble from './MessageBubble';
import { Loader } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
  command?: string;
  result?: any;
  error?: string;
}

interface ChatAreaProps {
  messages: Message[];
  isLoading: boolean;
}

const ChatArea = forwardRef<HTMLDivElement, ChatAreaProps>(
  ({ messages, isLoading }, ref) => {
    return (
      <div className="chat-area">
        <div className="messages-container">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h2>No messages yet</h2>
              <p>Start by sending a message to your agent</p>
            </div>
          ) : (
            <>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              {isLoading && (
                <div className="loading-indicator">
                  <Loader size={20} className="spinner" />
                  <span>Agent is thinking...</span>
                </div>
              )}
            </>
          )}
          <div ref={ref} />
        </div>
      </div>
    );
  }
);

ChatArea.displayName = 'ChatArea';

export default ChatArea;
