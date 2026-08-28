"""System prompts for LLM-backed answer paths.

Java parity: constants/SystemConstants.java (a373082 moved the inline RAG
prompts here so runtime behaviour and tests share one source of truth).
"""

from __future__ import annotations

RAG_ANSWER_SYSTEM = "你是一个RAG问答助手。必须仅根据给定上下文作答，输出结尾附上引用编号，例如 [1][2]。如果上下文不足请明确说明。"

HYBRID_RAG_ANSWER_SYSTEM = "你是一个企业级RAG问答助手。必须仅根据给定上下文作答，输出结尾附上引用编号，例如 [1][2]。如果上下文不足请明确说明。"
