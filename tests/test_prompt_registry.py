import pytest
from src.utils.prompt_registry import PromptRegistry, PromptVersion
import fakeredis

@pytest.fixture
def registry():
    # Fakeredis kullanarak bellek içi sanal redis ile testi izole ediyoruz
    r = fakeredis.FakeStrictRedis()
    return PromptRegistry(r)

def test_register_and_get_active(registry):
    # İlk prompt kaydı (varsayılan olarak candidate vb yerine "active" istersek)
    p1 = registry.register_prompt("test_agent", "Eski Prompt", "active")
    assert p1.status == "active"
    
    # Active'i getir
    active = registry.get_active_prompt("test_agent")
    assert active is not None
    assert active.content == "Eski Prompt"
    
def test_activate_candidate_retires_old(registry):
    # Bir active bir candidate prompt kaydet
    p1 = registry.register_prompt("test_agent", "İlk Prompt", "active")
    p2 = registry.register_prompt("test_agent", "İkinci Aday", "candidate")
    
    # Candidate'i activate et
    success = registry.activate_prompt("test_agent", p2.id)
    
    assert success is True
    
    # Eski prompt retired olmalı
    old_prompt_json = registry.redis.hget(registry._get_key("test_agent"), p1.id)
    import json
    old_prompt_data = json.loads(old_prompt_json)
    assert old_prompt_data["status"] == "retired"
    
    # Yeni active prompt gerçekten p2 mi?
    new_active = registry.get_active_prompt("test_agent")
    assert new_active.id == p2.id
    assert new_active.content == "İkinci Aday"
