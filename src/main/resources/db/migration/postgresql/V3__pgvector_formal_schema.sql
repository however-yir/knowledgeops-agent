CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ai_knowledge_chunks (
  id BIGSERIAL PRIMARY KEY,
  content TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding VECTOR(1024) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_knowledge_chunks_chat_id
  ON ai_knowledge_chunks ((metadata->>'chat_id'));

CREATE INDEX IF NOT EXISTS idx_ai_knowledge_chunks_file_name
  ON ai_knowledge_chunks ((metadata->>'file_name'));

CREATE INDEX IF NOT EXISTS idx_ai_knowledge_chunks_embedding_ivfflat
  ON ai_knowledge_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
