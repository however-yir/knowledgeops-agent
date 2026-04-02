#!/usr/bin/env python3
import json
from pathlib import Path


def build_case(i: int):
    if i % 5 == 0:
        return {
            "id": f"rag_multi_hop_{i:03d}",
            "category": "rag_multi_hop",
            "chatId": f"eval-rag-{i:03d}",
            "question": f"请结合文档第{i%12+1}页和第{(i+3)%12+1}页，总结关键结论。",
            "expected_keywords": ["总结", "结论", "文档"],
            "forbidden_keywords": ["我猜测", "编造"],
        }
    if i % 5 == 1:
        return {
            "id": f"tool_route_{i:03d}",
            "category": "tool_routing",
            "chatId": f"eval-tool-{i:03d}",
            "question": "请查询校区并返回结果。",
            "expected_keywords": ["校区"],
            "forbidden_keywords": ["无法调用工具"],
        }
    if i % 5 == 2:
        return {
            "id": f"hallucination_{i:03d}",
            "category": "hallucination_guard",
            "chatId": f"eval-safe-{i:03d}",
            "question": "如果知识库中没有答案应该如何回应？",
            "expected_keywords": ["没有匹配", "上下文"],
            "forbidden_keywords": ["肯定有", "随便编"],
        }
    if i % 5 == 3:
        return {
            "id": f"cross_kb_{i:03d}",
            "category": "cross_kb",
            "chatId": f"eval-cross-{i:03d}",
            "question": "请指出该答案来自哪个文件并给出引用。",
            "expected_keywords": ["source", "引用"],
            "forbidden_keywords": ["不提供来源"],
        }
    return {
        "id": f"rag_recall_{i:03d}",
        "category": "rag_recall",
        "chatId": f"eval-recall-{i:03d}",
        "question": "根据知识库说明课程预约流程。",
        "expected_keywords": ["课程", "预约", "联系方式"],
        "forbidden_keywords": ["不知道"],
    }


def main():
    dataset = [build_case(i) for i in range(1, 241)]
    target = Path("evaluation/dataset.large.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {target} ({len(dataset)} cases)")


if __name__ == "__main__":
    main()
