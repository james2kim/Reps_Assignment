import { useEffect, useState } from 'react';
import { fetchCompanies } from '../api';

export default function CompanySelect({ value, onChange }) {
  const [companies, setCompanies] = useState([]);

  useEffect(() => {
    fetchCompanies().then(setCompanies);
  }, []);

  return (
    <div className="select-group">
      <label>Company</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select a company...</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
}
