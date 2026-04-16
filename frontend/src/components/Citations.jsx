export default function Citations({ citations }) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="citations">
      <h4>Sources</h4>
      <div className="citation-list">
        {citations.map((c, i) => (
          <span key={i} className={`citation-chip ${c.source_type}`} title={c.source_file}>
            {c.label}
          </span>
        ))}
      </div>
    </div>
  );
}
