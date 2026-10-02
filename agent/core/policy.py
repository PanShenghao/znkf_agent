"""
文件职能: 升级策略（EscalationPolicy）—— 把「何时转人工」的所有阈值与触发器集中到一处（可审计）。
借鉴 ledgerly（阈值集中一个 config）+ ai-ticket-triage（升级=策略对象+显式触发，不是 prompt 里的兜底话术）。

两条「门」：
  1) 路由门 detect_rule_escalation()：确定性规则（欺诈 > 法律 > 转人工），在 LLM 之前命中（orchestrator 调用）。
  2) 执行门 decide_execution_escalation()：熔断 / 连续失败 / 空回复（chat_service 调用）。
"""
import re
from dataclasses import dataclass
from enum import Enum


class EscalationTrigger(str, Enum):
    RULE_FRAUD = "rule_fraud"
    RULE_LEGAL = "rule_legal"
    RULE_HUMAN_REQUEST = "rule_human_request"
    CIRCUIT_OPEN = "circuit_open"
    CONSECUTIVE_FAILURES = "consecutive_failures"
    EMPTY_RESPONSE = "empty_response"
    UNGROUNDED = "ungrounded"


@dataclass(frozen=True)
class EscalationDecision:
    trigger: EscalationTrigger
    reason: str


@dataclass(frozen=True)
class EscalationPolicy:
    """所有升级阈值集中在此（评审者一处可见，值来自 settings，可 env 覆盖）。"""
    consecutive_failure_threshold: int = 3   # 连续失败 N 次 → 转人工
    circuit_failure_threshold: int = 3       # 熔断器失败阈值
    circuit_reset_timeout: int = 60          # 熔断冷却秒
    min_response_chars: int = 12             # 回答短于该长度视为无效 → 升级
    turn_limit: int = 8                      # 会话轮数上限（预留）
    frustration_threshold: int = 2           # 沮丧情绪次数（预留）

    @classmethod
    def from_settings(cls) -> "EscalationPolicy":
        from config import get_settings

        s = get_settings()
        return cls(
            consecutive_failure_threshold=s.human_escalation_threshold,
            circuit_failure_threshold=s.cb_failure_threshold,
            circuit_reset_timeout=s.cb_reset_timeout,
        )


# ---- 确定性升级规则（在 LLM 之前命中，ledgerly 模式）----
# 注意：「人工」不作为独立关键词，避免「人工智能」被误判为要转人工。

_FRAUD_RE = re.compile(
    r"(盗刷|被盗|诈骗|欺诈|盗用|不是我刷的|unauthorized|stolen|fraud|hacked)",
    re.IGNORECASE,
)
_LEGAL_RE = re.compile(
    r"(律师|起诉|诉讼|法院|告你|法律|lawyer|attorney|lawsuit|legal action|\bsue\b|\bsuing\b)",
    re.IGNORECASE,
)
_HUMAN_RE = re.compile(
    r"(转人工|人工客服|人工服务|找人工|我要人工|转接人工|真人|"
    r"\bhuman\b|\breal (person|agent)\b|\brepresentative\b)",
    re.IGNORECASE,
)


def detect_rule_escalation(text: str):
    """路由门：确定性规则检测（欺诈 > 法律 > 转人工，first-match-wins）。
    返回 (EscalationTrigger, reason) 或 None。"""
    if _FRAUD_RE.search(text):
        return EscalationTrigger.RULE_FRAUD, "疑似欺诈/盗刷主张"
    if _LEGAL_RE.search(text):
        return EscalationTrigger.RULE_LEGAL, "涉及法律/诉讼主张"
    if _HUMAN_RE.search(text):
        return EscalationTrigger.RULE_HUMAN_REQUEST, "用户明确要求转人工"
    return None


def decide_execution_escalation(
    *,
    breaker_open: bool,
    consecutive_failures: int,
    response_text: str | None,
    policy: EscalationPolicy,
) -> EscalationDecision | None:
    """执行门：按优先级判定是否升级（熔断 > 连续失败 > 空回复）。"""
    if breaker_open:
        return EscalationDecision(EscalationTrigger.CIRCUIT_OPEN, "LLM 服务熔断")
    if consecutive_failures >= policy.consecutive_failure_threshold:
        return EscalationDecision(
            EscalationTrigger.CONSECUTIVE_FAILURES, f"连续 {consecutive_failures} 次调用失败"
        )
    if response_text is not None and len(response_text.strip()) < policy.min_response_chars:
        return EscalationDecision(EscalationTrigger.EMPTY_RESPONSE, "回答为空或过短，视为无效")
    return None


def decide_grounding_escalation(*, is_rag_turn: bool, any_evidence: bool) -> EscalationDecision | None:
    """反幻觉门：RAG 类问题且本轮未检索到证据 → 升级（拒绝编造）。"""
    if is_rag_turn and not any_evidence:
        return EscalationDecision(EscalationTrigger.UNGROUNDED, "检索无证据，拒绝编造")
    return None
