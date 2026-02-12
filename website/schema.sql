DROP TABLE IF EXISTS submissions;
CREATE TABLE submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  story_id TEXT,             -- 剧情 ID (如 101101)
  original_filename TEXT,    -- 提交时对应的原始文件名
  category TEXT,             -- 分类目录
  content TEXT,              -- 汉化文本内容
  author TEXT,               -- 贡献者
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);