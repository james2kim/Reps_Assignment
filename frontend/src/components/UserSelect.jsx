import { useEffect, useState } from 'react';
import { fetchUsers } from '../api';

export default function UserSelect({ companyId, value, onChange }) {
  const [users, setUsers] = useState([]);

  useEffect(() => {
    if (!companyId) {
      setUsers([]);
      return;
    }
    fetchUsers(companyId).then(setUsers);
  }, [companyId]);

  return (
    <div className="select-group">
      <label>User</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={!companyId}>
        <option value="">Select a user...</option>
        {users.map((u) => (
          <option key={u.id} value={u.id}>
            {u.display_name} ({u.username})
          </option>
        ))}
      </select>
    </div>
  );
}
