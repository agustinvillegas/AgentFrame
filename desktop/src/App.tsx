import React, { useState, useEffect, useRef } from 'react';
import axios, { AxiosError } from 'axios';
import ChatArea from './components/ChatArea';
import InputArea from './components/InputArea';
import CommandPanel from './components/CommandPanel';
import InitialSetup from './components/InitialSetup';
import Header from './components/Header';
import './App.css';

interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
  command?: string;
  result?: any;
  error?: string;
}

interface ApiError {
  detail?: string;
  message?: string;
}

const API_BASE = 'http://127.0.0.1:5000';

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [apiKey, setApiKey] = useState<string>('');
  const [showCommandPanel, setShowCommandPanel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleInit = async (key: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await axios.post(`${API_BASE}/init`, { api_key: key });

      if (response.status === 200) {
        setApiKey(key);
        setIsInitialized(true);
        // Add welcome message
        setMessages([
          {
            id: '0',
            role: 'agent',
            content: '¡Hola! Soy tu asistente de AgentShell. Puedo controlar tu PC de Windows. ¿Qué necesitas que haga?',
            timestamp: new Date(),
          },
        ]);
      }
    } catch (err) {
      const axiosError = err as AxiosError<ApiError>;
      const errorMsg =
        axiosError.response?.data?.detail ||
        (err instanceof Error ? err.message : 'Error de inicialización');
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    try {
      setIsLoading(true);
      setError(null);

      // Add user message
      const userMessage: Message = {
        id: Date.now().toString(),
        role: 'user',
        content: text,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Send to backend
      const response = await axios.post(`${API_BASE}/message`, {
        message: text,
        api_key: apiKey,
        });

      // Add agent response
      const agentMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'agent',
        content: response.data.agent_reply,
        timestamp: new Date(),
        command: response.data.command_executed,
        result: response.data.command_result,
        error: response.data.error,
      };
      setMessages((prev) => [...prev, agentMessage]);
    } catch (err) {
      const axiosError = err as AxiosError<ApiError>;
      const errorMsg =
        axiosError.response?.data?.detail ||
        (err instanceof Error ? err.message : 'Error al enviar mensaje');
      setError(errorMsg);

      // Add error message
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: 'agent',
        content: `Error: ${errorMsg}`,
        timestamp: new Date(),
        error: errorMsg,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearChat = async () => {
    try {
      await axios.post(`${API_BASE}/clear`);
      setMessages([]);
    } catch (err) {
      console.error('Error clearing chat:', err);
    }
  };

  if (!isInitialized) {
    return <InitialSetup onInit={handleInit} isLoading={isLoading} error={error} />;
  }

  return (
    <div className="app">
      <Header
        onToggleCommandPanel={() => setShowCommandPanel(!showCommandPanel)}
        onClearChat={handleClearChat}
      />
      <div className="main-container">
        {showCommandPanel && <CommandPanel />}
        <div className="chat-container">
          <ChatArea messages={messages} isLoading={isLoading} ref={chatEndRef} />
          <InputArea
            onSendMessage={handleSendMessage}
            isLoading={isLoading}
            error={error}
          />
        </div>
      </div>
    </div>
  );
};

export default App;
