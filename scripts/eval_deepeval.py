"""
DeepEval 评测：用 LLM-as-Judge 给客服回答打质量分（相关性 + 忠实度）。
配合 scripts/eval_test.py（确定性断言：转人工/越权/报错/耗时）一起构成评测门禁。

用法：.venv/Scripts/python.exe scripts/eval_deepeval.py
说明：
  - 需要 deepeval 已安装（pip install deepeval）
  - 评委模型复用 DASHSCOPE_API_KEY（通义千问 OpenAI 兼容接口），不额外申请 Key
  - 商品/RAG 类问题会用 demo_data 知识库作为 retrieval_context 做「忠实度」校验（反幻觉）
"""
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv
load_dotenv(PROJECT_DIR / "agent" / ".env")

DASHSCOPE_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE = os.getenv("BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
JUDGE_MODEL = os.getenv("MODEL", "qwen-plus")


def _load_kb_context() -> str:
    parts = []
    for f in sorted((PROJECT_DIR / "demo_data").glob("*.md")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


KB_CONTEXT = _load_kb_context()

# (名称, 问题, 是否RAG类[需忠实度上下文], 期望关键词弱校验)
TEST_CASES = [
    ("商品咨询-向量", "什么是主动降噪？", True, ["降噪"]),
    ("商品咨询-图谱", "iPhone 15 Pro 内存多大？", True, ["8GB", "8 GB", "内存"]),
    ("关系查询", "小米有哪些手机？", True, ["小米", "手机"]),
    ("政策查询", "七天无理由退货有什么条件？", True, ["退货", "7天", "七日"]),
    ("订单查询", "帮我查一下我最近的订单", False, ["订单"]),
    ("优惠活动", "现在有什么优惠券？", False, ["优惠"]),
    ("商品推荐", "预算5000买什么手机？", True, []),
    ("比价对比", "iPhone 15 和小米14 哪个好？", True, []),
]


def run_agent(query: str) -> str:
    r = subprocess.run(
        [sys.executable, "agent/main.py", "-q", query],
        cwd=PROJECT_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    m = re.search(r"🤖 AI:\s*(.*)", r.stdout, re.DOTALL)  # 只取 stdout，避免混入 MCP/日志
    return m.group(1).strip() if m else ""


def main() -> int:
    try:
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        from deepeval.models import OpenAIModel
    except ImportError:
        print("未安装 deepeval：请先执行 pip install deepeval")
        return 1

    # 评委模型：复用通义千问（OpenAI 兼容），显式传 base_url（DeepEval 不读 OPENAI_BASE_URL 环境变量）
    judge = OpenAIModel(model=JUDGE_MODEL, api_key=DASHSCOPE_KEY, base_url=DASHSCOPE_BASE)

    print("=" * 60)
    print(f"DeepEval 评测（评委模型 {JUDGE_MODEL}）")
    print("=" * 60)

    passed = 0
    total = 0
    for name, query, is_rag, keywords in TEST_CASES:
        answer = run_agent(query)
        print(f"\n[{name}] 问: {query}")
        print(f"  答(前100字): {answer[:100]}")

        if not answer:
            print("  ⛔ 无回答，跳过")
            continue

        test_case = LLMTestCase(
            input=query,
            actual_output=answer,
            retrieval_context=[KB_CONTEXT] if is_rag else [],
        )
        metrics = [AnswerRelevancyMetric(threshold=0.6, model=judge)]
        if is_rag:
            metrics.append(FaithfulnessMetric(threshold=0.6, model=judge))

        case_ok = True
        for m in metrics:
            total += 1
            try:
                m.measure(test_case)
                ok = m.score is not None and m.score >= m.threshold
                if not ok:
                    case_ok = False
                else:
                    passed += 1
                flag = "✅" if ok else "❌"
                print(f"    {m.__class__.__name__}: {m.score:.2f} (阈值 {m.threshold}) {flag}")
                if not ok and m.reason:
                    print(f"      理由: {m.reason[:200]}")
            except Exception as e:
                case_ok = False
                print(f"    {m.__class__.__name__}: 评测异常 {e}")

        # 确定性弱校验：期望关键词未命中 → 判定跑偏
        if keywords and not any(k in answer for k in keywords):
            case_ok = False
            print(f"    ❌ 期望关键词 {keywords} 未命中")

    print("\n" + "=" * 60)
    print(f"汇总: {passed}/{total} 项指标达标")
    print("=" * 60)
    return 0 if (total and passed == total) else 1


if __name__ == "__main__":
    raise SystemExit(main())
