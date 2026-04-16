import { useState, useRef } from 'react';
import { searchStream } from './api';
import CompanySelect from './components/CompanySelect';
import UserSelect from './components/UserSelect';
import SearchBar from './components/SearchBar';
import AnswerStream from './components/AnswerStream';
import ThoughtTrace from './components/ThoughtTrace';
import Citations from './components/Citations';
import './App.css';

export default function App() {
  const [companyId, setCompanyId] = useState('');
  const [userId, setUserId] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState([]);
  const [trace, setTrace] = useState(null);
  const [disclaimer, setDisclaimer] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const controllerRef = useRef(null);

  const handleCompanyChange = (id) => {
    setCompanyId(id);
    setUserId('');
    clearResults();
  };

  const clearResults = () => {
    setAnswer('');
    setCitations([]);
    setTrace(null);
    setDisclaimer(null);
    setError(null);
  };

  const handleSearch = (query) => {
    if (controllerRef.current) {
      controllerRef.current.abort();
    }

    clearResults();
    setIsStreaming(true);

    controllerRef.current = searchStream(companyId, userId, query, (event) => {
      switch (event.type) {
        case 'trace':
          setTrace(event);
          break;
        case 'citation':
          setCitations((prev) => [...prev, event]);
          break;
        case 'token':
          setAnswer((prev) => prev + event.text);
          break;
        case 'disclaimer':
          setDisclaimer(event.text);
          break;
        case 'done':
          setIsStreaming(false);
          break;
        case 'error':
          setError(event.text);
          setIsStreaming(false);
          break;
      }
    });
  };

  const ready = companyId && userId;

  return (
    <div className="app">
      <header className="header">
        <h1>BigSpring Search</h1>
        <p className="subtitle">Secure multi-tenant enterprise search engine</p>
      </header>

      <div className="context-bar">
        <CompanySelect value={companyId} onChange={handleCompanyChange} />
        <UserSelect companyId={companyId} value={userId} onChange={setUserId} />
      </div>

      <SearchBar onSearch={handleSearch} disabled={!ready || isStreaming} />

      {error && <div className="error-banner">{error}</div>}

      <div className="results">
        <ThoughtTrace trace={trace} />
        <AnswerStream answer={answer} isStreaming={isStreaming} disclaimer={disclaimer} />
        <Citations citations={citations} />
      </div>
    </div>
  );
}
