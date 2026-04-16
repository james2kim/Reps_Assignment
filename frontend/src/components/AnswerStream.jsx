import { useRef, useEffect } from 'react';

export default function AnswerStream({ answer, isStreaming, disclaimer }) {
  const containerRef = useRef(null);

  // Smoothly scroll to bottom as content grows
  useEffect(() => {
    if (containerRef.current && isStreaming) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [answer, isStreaming]);

  if (!answer && !isStreaming) return null;

  // Split into paragraphs on double newlines, render as block elements
  const paragraphs = answer ? answer.split(/\n\n+/) : [];

  return (
    <div className="answer-container" ref={containerRef}>
      {isStreaming && !answer && (
        <div className="loading-indicator">Searching and generating answer...</div>
      )}
      <div className="answer-text">
        {paragraphs.map((p, i) => (
          <p key={i} className="answer-paragraph">
            {p.split('\n').map((line, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {line}
              </span>
            ))}
          </p>
        ))}
        {isStreaming && <span className="cursor" aria-hidden="true" />}
      </div>
      {disclaimer && !isStreaming && (
        <div className="disclaimer">{disclaimer}</div>
      )}
    </div>
  );
}
