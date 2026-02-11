DROP TABLE IF EXISTS submissions;
CREATE TABLE submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  story_id TEXT,
  content TEXT,
  author TEXT,
  status TEXT DEFAULT 'pending', -- pending, approved, rejected
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);