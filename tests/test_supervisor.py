import pytest
from unittest.mock import patch, MagicMock
from src.state import AgentState
from src.graph import check_supervisor_route

def test_supervisor_route_full_pipeline():
    """Supervisor 'full_pipeline' komutunda Collector rotasını seçmeli"""
    state: AgentState = {"user_goal": "full_pipeline"}
    route = check_supervisor_route(state)
    assert route == "Collector"

def test_supervisor_route_only_ideate():
    """Supervisor 'only_ideate' komutunda Extractor rotasını seçmeli"""
    state: AgentState = {"user_goal": "only_ideate"}
    route = check_supervisor_route(state)
    assert route == "Extractor"

def test_supervisor_route_only_report():
    """Supervisor 'only_report' komutunda Gate/Writer rotasını seçmeli"""
    state: AgentState = {"user_goal": "only_report"}
    route = check_supervisor_route(state)
    assert route == "ObsidianGate"

def test_supervisor_route_default():
    """Bilinmeyen modda full_pipeline default edilmeden önce graf'ta collector seçilmeli"""
    state: AgentState = {}
    route = check_supervisor_route(state)
    assert route == "Collector"
