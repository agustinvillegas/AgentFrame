import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './CommandPanel.css';
import { ChevronDown, Copy } from 'lucide-react';

interface Command {
  group: string;
  name: string;
  params: string;
  description?: string;
}

const CommandPanel: React.FC = () => {
  const [commands, setCommands] = useState<Command[]>([]);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    const fetchSchema = async () => {
      try {
        const response = await axios.get('http://127.0.0.1:5000/schema');
        const schema = response.data.schema;

        const commandList: Command[] = [];
        for (const group in schema) {
          for (const cmd in schema[group]) {
            const info = schema[group][cmd];
            const params = Object.entries(info.params || {})
              .map(([p, v]: [string, any]) => {
                if (v.required) {
                  return `--${p}(required)`;
                } else {
                  return `--${p}[=${v.default}]`;
                }
              })
              .join(' ');

            commandList.push({
              group,
              name: cmd,
              params,
              description: info.description,
            });
          }
        }

        setCommands(commandList);
        if (commandList.length > 0) {
          setExpandedGroup(commandList[0].group);
        }
      } catch (err) {
        console.error('Error fetching schema:', err);
      }
    };

    fetchSchema();
  }, []);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(text);
    setTimeout(() => setCopied(null), 2000);
  };

  const groups = Array.from(new Set(commands.map((c) => c.group)));

  return (
    <div className="command-panel">
      <h3 className="panel-title">Available Commands</h3>
      <div className="commands-list">
        {groups.map((group) => (
          <div key={group} className="command-group">
            <button
              className="group-header"
              onClick={() =>
                setExpandedGroup(expandedGroup === group ? null : group)
              }
            >
              <ChevronDown
                size={16}
                className={`chevron ${expandedGroup === group ? 'open' : ''}`}
              />
              <span className="group-name">{group}</span>
            </button>

            {expandedGroup === group && (
              <div className="group-commands">
                {commands
                  .filter((c) => c.group === group)
                  .map((cmd) => (
                    <div key={`${cmd.group}-${cmd.name}`} className="command-item">
                      <div className="command-signature">
                        <code className="cmd-name">{cmd.name}</code>
                        <code className="cmd-params">{cmd.params}</code>
                      </div>
                      {cmd.description && (
                        <p className="cmd-description">{cmd.description}</p>
                      )}
                      <button
                        className="copy-cmd-btn"
                        onClick={() =>
                          handleCopy(`${cmd.group} ${cmd.name} ${cmd.params}`)
                        }
                      >
                        <Copy size={14} />
                        {copied === `${cmd.group} ${cmd.name} ${cmd.params}`
                          ? 'Copied'
                          : 'Copy'}
                      </button>
                    </div>
                  ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default CommandPanel;
