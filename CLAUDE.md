You are a senior staff ai engineer. 
I am building a take-home assignment: a secure multi-tenant search engine.

This is NOT a chatbot. It is a scoped enterprise search system.

Dataset:
- /data/database contains CSV/JSON files that define relational tables:
  companies, users, plays, play_assignments, reps, assets, submissions, feedback
- /data/assets contains structured JSON content for search (PDF pages, video transcripts, etc.)

Core requirements:
- User selects a company and then a user
- Search must be strictly scoped to:
  1. knowledge from watch reps in assigned plays
  2. that user’s own submissions and feedback
- Must NEVER expose:
  - other companies
  - unassigned plays
  - other users’ submissions

System behavior:
- authorization MUST happen before retrieval
- responses must follow:
  1. grounded answer (with citations)
  2. general professional fallback (with disclaimer)
  3. out-of-scope refusal
  4. proprietary no-grounding refusal

Tech:
- Postgres for relational data
- keep implementation minimal (time-boxed)
- avoid overengineering

Important:
Focus on correctness, clarity, and scoped retrieval — not infrastructure complexity.

Please keep all code simple, readable, and testable.