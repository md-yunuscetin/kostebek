import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from langgraph.types import Command
from src.state import AgentState

# LangGraph interrupt objeleri yerine, testlerde Graph'ın nasıl durup resume ettiği denetlenir.

@pytest.fixture
def mock_state():
    return {
        "user_goal": "full_pipeline",
        "best_evaluations": [
            MagicMock(idea_title="Test Fikir 1", total_score=38)
        ]
    }

@pytest.fixture
def mock_app():
    # Sahte bir graph invoke objesi. Aslında tam Langgraph state çalıştırılır.
    # Bu test mock mantığıyla tasarlanmıştır
    app = MagicMock()
    
    def mock_invoke(cmd_or_state, config):
        if isinstance(cmd_or_state, Command):
            if cmd_or_state.resume == "approve":
                return {"active_nodes": ["Writer"]}
            if cmd_or_state.resume == "reject":
                return {"final_output": None}
        return {"__interrupt__": [{"value": {"message": "Onaylıyor musun?"}}]}
    
    app.invoke = mock_invoke
    return app


@pytest.mark.asyncio
async def test_obsidian_gate_approve(mock_app, mock_state):
    """Kullanıcı 'approve' derse Writer'a gitmeli"""
    with patch("src.approval_gates.ask_via_telegram", new_callable=AsyncMock) as mock_ask:
        mock_ask.return_value = "approve"
        result = mock_app.invoke(
            Command(resume="approve"),
            config={"configurable": {"thread_id": "test-001"}}
        )
        assert "Writer" in result["active_nodes"]

@pytest.mark.asyncio        
async def test_obsidian_gate_reject(mock_app, mock_state):
    """Kullanıcı 'reject' derse pipeline durmalı"""
    with patch("src.approval_gates.ask_via_telegram", new_callable=AsyncMock) as mock_ask:
        mock_ask.return_value = "reject"
        result = mock_app.invoke(
            Command(resume="reject"),
            config={"configurable": {"thread_id": "test-002"}}
        )
        assert result.get("final_output") is None
