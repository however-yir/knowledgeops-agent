CREATE INDEX IF NOT EXISTS idx_ai_knowledge_chunks_tenant_id
  ON ai_knowledge_chunks ((metadata->>'tenant_id'));

CREATE INDEX IF NOT EXISTS idx_ai_knowledge_chunks_tenant_chat_id
  ON ai_knowledge_chunks ((metadata->>'tenant_id'), (metadata->>'chat_id'));
