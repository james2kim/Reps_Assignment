import { useState } from 'react';

export default function SearchBar({ onSearch, disabled }) {
  const [query, setQuery] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !disabled) {
      onSearch(query.trim());
    }
  };

  return (
    <form className="search-bar" onSubmit={handleSubmit}>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search your assigned materials..."
        disabled={disabled}
      />
      <button type="submit" disabled={disabled || !query.trim()}>
        Search
      </button>
    </form>
  );
}
