import pytest
from src.state import AgentState
from src.models import PainPoint, IdeaDraft, InvestmentMemo
from src.self_healer import SelfHealingOrchestrator
from src.self_improver import SelfImprovementAgent

# ==========================================
# TEMEL MODEL TESTLER (V4 & V5 Uyumlu)
# ==========================================

def test_pain_point_model_validation():
    """PainPoint pydantic şemasının doğru çalıştığını test eder."""
    valid_data = {
        "pain_id": "P-123",
        "theme": "Invoice Management",
        "user_segment": "Freelancers",
        "evidence_posts": ["https://reddit.com/r/freelance/1"],
        "urgency_score": 8,
        "monetizability_score": 9
    }

    pain = PainPoint(**valid_data)
    assert pain.pain_id == "P-123"
    assert pain.urgency_score == 8


def test_pain_point_invalid_score():
    """1-10 arası olmayan skorların Pydantic tarafından yakalandığını test eder."""
    invalid_data = {
        "pain_id": "P-124",
        "theme": "Bad UI",
        "user_segment": "Users",
        "evidence_posts": [],
        "urgency_score": 15,  # Invalid (>10)
        "monetizability_score": 5
    }

    with pytest.raises(ValueError):
        PainPoint(**invalid_data)


def test_initial_agent_state():
    """AgentState TypedDict yapısının doğru başlatılabildiğini test eder."""
    state: AgentState = {
        "raw_data": [{"title": "test", "score": 20}],
        "pain_points": [],
        "ideas": [],
        "evaluations": [],
        "approved_ideas": [],
        "final_output": "",
        "guard_feedback": "",
        "retry_count": 0,
        "error": None,
        "healing_attempts": 0
    }

    raw_data: list = state["raw_data"]  # explicit typing for Pyre2
    assert len(raw_data) == 1
    assert state["retry_count"] == 0


# ==========================================
# V5/V8 SELF-HEALER TESTLER
# ==========================================

def test_healer_diagnose_api_quota():
    """Self-Healer'ın API kota hatasında switch_model action döndürdüğünü test eder."""
    healer = SelfHealingOrchestrator()
    state: AgentState = {
        "raw_data": [], "pain_points": [], "ideas": [], "evaluations": [],
        "approved_ideas": [], "final_output": "", "guard_feedback": "",
        "retry_count": 0, "error": "Error 429: rate limit exceeded", "healing_attempts": 0
    }
    outcome = healer.diagnose(str(state["error"]), state)
    assert outcome.action == "switch_model"
    assert outcome.healed is True


def test_healer_diagnose_json_error():
    """Self-Healer'ın JSON parse hatasında lower_temperature action döndürdüğünü test eder."""
    healer = SelfHealingOrchestrator()
    state: AgentState = {
        "raw_data": [{"some": "data"}], "error": "json parse failed"
    }
    outcome = healer.diagnose(str(state["error"]), state)
    assert outcome.action == "lower_temperature"
    assert outcome.healed is True

def test_healer_diagnose_empty_scraper():
    """Boş data dönmesi durumunda test."""
    healer = SelfHealingOrchestrator()
    state: AgentState = {
        "raw_data": [], "error": "empty_scraper: no data"
    }
    outcome = healer.diagnose(str(state["error"]), state)
    assert outcome.action == "relax_filters"
    assert outcome.healed is True

def test_healer_diagnose_unrecoverable():
    """Self-Healer'ın tanımlanamayan bir hatada abort döndürdüğünü test eder."""
    healer = SelfHealingOrchestrator()
    state: AgentState = {
        "raw_data": [{"some": "data"}], "error": "unknown critical system fault"
    }
    outcome = healer.diagnose(str(state["error"]), state)
    assert outcome.action == "abort"
    assert outcome.healed is False


# ==========================================
# V5 IMPROVER COMPUTE TOTAL SCORE TEST
# ==========================================

def test_improver_compute_total_score():
    """Self-Improver'ın InvestmentMemo alt puanlarını toplayabildiğini test eder."""
    improver = SelfImprovementAgent()
    memo = InvestmentMemo(
        idea_id="I-001",
        market_need_score=8,
        feasibility_score=7,
        competition_score=6,
        audience_clarity_score=9,
        risk_score=5,
        analysis="Test analizi."
    )

    total = memo.market_need_score + memo.feasibility_score + memo.competition_score + memo.audience_clarity_score + memo.risk_score
    assert total == 35
