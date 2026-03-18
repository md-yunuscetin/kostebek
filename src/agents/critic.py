from typing import Dict, Any, List
from pydantic import BaseModel
from src.state import AgentState
from src.models import InvestmentMemo
from src.agents.base import get_llm
from src.utils.logger import get_logger
from src.utils.prompt_registry import get_registry

logger = get_logger("critic")

class CriticOutput(BaseModel):
    evaluations: List[InvestmentMemo]

def run_critic_agent(state: AgentState) -> Dict[str, Any]:
    """İş fikirlerini (IdeaDraft) yatırımcı gözüyle eleştirir ve skorlar (Subagent)"""
    logger.info("[AGENT] Critic: Fikirler rasyonel bir yatırımcı gözüyle puanlanıyor...")
    ideas = state.get("ideas", [])

    if not ideas:
        logger.warning("[AGENT] Critic: Puanlanacak fikir bulunamadı.")
        return {"evaluations": []}

    llm = get_llm(temperature=0.2)
    structured_llm = llm.with_structured_output(CriticOutput)

    fallback_prompt = """Sen deneyimli bir yatırım komitesisin. Ekibinde üç profil var:
1. Ex-Klinisyen & HealthTech Yatırımcısı (a16z Bio, Rock Health deneyimi)
2. EdTech Girişimcisi & Eğitim Politikası Uzmanı
3. Seri Teknoloji Girişimcisi (SaaS, B2B, platform modelleri)

GÖREV:
Sana verilen iş fikirlerini, alanına özel kriterlerle değerlendir.
Her fikre asagidaki 5 ORTAK + 2 ALAN-SPESIFIK kriter üzerinden 1-10 puan ver.

5 ORTAK KRITER:
1. Market Need - Sorun ne kadar yaygin ve aci verici?
2. Feasibility - 6-12 ayda MVP cikilab ilir mi?
3. Competition - Mevcut oyuncular kim? Diferansiator ne?
4. Audience Clarity - Ilk 100 musteriy i nerede bulursun?
5. Risk Score - (10=risksiz, 1=cok riskli)

ALAN-SPESIFIK KRITERLER:

TIP & SAGLIK ise:
6a. Regulatory Pathway [1-10]
    - Wellness uygulamasi: 8-10
    - Klinik karar destek: 4-6
    - Tibbi cihaz: 1-3
6b. Clinical Validation Need [1-10]
    - Kanit gerekmez: 8-10
    - Pilot yeterli: 5-7
    - RCT zorunlu: 1-4

EGITIM ise:
6a. Pedagogical Soundness [1-10]
    - Aktif ogrenme/spaced repetition: 8-10
    - Pasif video/okuma: 4-6
    - Oyunlastirma ama kanit yok: 2-4
6b. Adoption Friction [1-10]
    - B2C direkt: 8-10
    - Ogretmen kanali: 5-7
    - Mufredat entegrasyonu: 2-4

7. Timing Score [1-10] - Google Trends + sektor gelismeleri

KURALLAR:
- Tum fikirleri degerlendir
- Medikal fikirde Regulatory 3 altindaysa uyari yaz
- Egitim fikirinde pedagojik kanit yoksa belirt
- Analiz Turkce yaz
- SADECE InvestmentMemo formatinda schema dondur"""

    CRITIC_PROMPT_VERSION = "v2.1-health-education"

    registry = get_registry()
    active_prompt_obj = registry.get_active_prompt("critic") if registry else None

    if active_prompt_obj:
        is_outdated = not active_prompt_obj.notes or \
                      CRITIC_PROMPT_VERSION not in active_prompt_obj.notes
        if is_outdated:
            logger.info(f"[AGENT] Critic: Eski prompt guncelleniyor -> {CRITIC_PROMPT_VERSION}")
            registry.register_prompt(
                "critic", fallback_prompt, status="active",
                notes=f"Health/Education domain-specific | {CRITIC_PROMPT_VERSION}"
            )
            system_prompt = fallback_prompt
        else:
            system_prompt = active_prompt_obj.content
            logger.info(f"[AGENT] Critic: Registry'den aktif prompt yuklendi ({CRITIC_PROMPT_VERSION})")
    else:
        system_prompt = fallback_prompt
        if registry:
            registry.register_prompt(
                "critic", fallback_prompt, status="active",
                notes=f"Health/Education domain-specific | {CRITIC_PROMPT_VERSION}"
            )

    from src.tools.gtrends_tools import get_trend_score

    user_content = "FIKIRLER HAVUZU:\n"
    for idea in ideas:
        trend_kw = " ".join(idea.title.split()[:2])
        trend_val = get_trend_score(trend_kw)
        idea.trend_score = trend_val
        user_content += (
            f"\n- Fikir ID: {idea.idea_id}\n"
            f"  Baslik: {idea.title}\n"
            f"  Problem: {idea.problem}\n"
            f"  Cozum: {idea.solution}\n"
            f"  Wedge: {idea.wedge}\n"
            f"  Hedef Kitle: {idea.target_audience}\n"
            f"  Google Trends Puani: {trend_val}/100\n"
        )

    try:
        result = structured_llm.invoke(system_prompt + "\n\n" + user_content)
        if hasattr(result, 'usage_metadata') and result.usage_metadata:
            logger.debug(f"[Critic] Token -> Input: {result.usage_metadata.input_tokens}, Output: {result.usage_metadata.output_tokens}")
        logger.info(f"[AGENT] Critic: {len(result.evaluations)} fikir detaylandirildi.")
        return {"evaluations": result.evaluations}
    except Exception as e:
        logger.error(f"[AGENT] Critic Hatasi: {e}")
        return {"evaluations": []}
