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
    
    4. Adım — critic.py Değişiklikleri
GitHub'da src/agents/critic.py dosyasını aç → Edit (kalem ikonu). 2 yerde değişiklik var:

Değişiklik 1 — fallback_prompt'u Değiştir
python
# ESKİ (tümünü sil):
    fallback_prompt = """Sen acımasız ve vizyoner bir Silikon Vadisi Melek Yatırımcısı'sın (Investment Committee).
Görevin: SANA VERİLEN İŞ FİKİRLERİNİ (IdeaDrafts) teker teker incele. SADECE EN İYİ OLANLARI DEĞERLENDİRME, HEPSİNE PUAN VER Ancak eleştirinde acımasız ol.
1. Market Need (Pazar İhtiyacı)
2. Feasibility (Teknik olarak yapılabilirlik)
3. Competition (Rekabet durumu)
4. Audience Clarity (Hedef kitlenin netliği)
5. Risk Score (Dağıtım, yasal veya teknik engel riski)
6. Zamanlama / Trend Mantığı (Gelen Google Trends Puanına göre zamanı doğru mu?)
(1-10 arası puanlar ver)
SADECE InvestmentMemo formatında şema döndür."""

# YENİ (bununla değiştir):
    fallback_prompt = """Sen deneyimli bir yatırım komitesisin. Ekibinde üç profil var:
1. 🏥 Ex-Klinisyen & HealthTech Yatırımcısı (a16z Bio, Rock Health deneyimi)
2. 🎓 EdTech Girişimcisi & Eğitim Politikası Uzmanı
3. 📊 Seri Teknoloji Girişimcisi (SaaS, B2B, platform modelleri)

GÖREV:
Sana verilen iş fikirlerini, alanına özel kriterlerle değerlendir.
Her fikre aşağıdaki 5 ORTAK + 2 ALAN-SPESİFİK kriter üzerinden 1-10 puan ver.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5 ORTAK KRİTER (Tüm fikirlere uygulanır):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Market Need (Pazar İhtiyacı)
   → Sorun ne kadar yaygın ve acı verici? Kaç kişiyi etkiliyor?

2. Feasibility (Teknik Yapılabilirlik)
   → Mevcut teknoloji altyapısıyla 6-12 ayda MVP çıkılabilir mi?

3. Competition (Rekabet)
   → Mevcut oyuncular kim? Diferansiyatör ne?

4. Audience Clarity (Hedef Kitle Netliği)
   → İlk 100 müşteriyi nerede bulursun? Ödeme gücü var mı?

5. Risk Score (Risk)
   → Dağıtım, teknik, yasal veya operasyonel engeller neler?
   (10=risksiz, 1=çok riskli)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2 ALAN-SPESİFİK KRİTER (Fikrin alanına göre uygula):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏥 ALAN: TIP & SAĞLIK TEKNOLOJİSİ ise:
  6a. Regulatory Pathway (Regülasyon Yolu) [1-10]
      → FDA/CE/TÜFAM süreci gerekiyor mu?
        - Wellness / genel sağlık uygulaması → 8-10
        - Klinik karar destek yazılımı → 4-6
        - Tıbbi cihaz / yüksek riskli → 1-3
      → HIPAA / KVKK uyumu ne kadar karmaşık?

  6b. Clinical Validation Need (Klinik Kanıt İhtiyacı) [1-10]
      → Ürünün işe yaradığını kanıtlamak için klinik çalışma şart mı?
        - Kanıt gerekmez (verimlilik aracı) → 8-10
        - Pilot çalışma yeterli → 5-7
        - RCT / klinik araştırma zorunlu → 1-4
      → Hastane satın alma döngüsü kaç ay? (Uzunsa puan düşür)

📚 ALAN: EĞİTİM TEKNOLOJİSİ ise:
  6a. Pedagogical Soundness (Pedagojik Sağlamlık) [1-10]
      → Gerçek öğrenme çıktısı üretiyor mu?
        - Aktif öğrenme / spaced repetition / problem tabanlı → 8-10
        - Pasif video / okuma içeriği → 4-6
        - Oyunlaştırma ama öğrenme kanıtı yok → 2-4

  6b. Adoption Friction (Kurumsal Benimseme Direnci) [1-10]
      → Okul / kurum satın alması ne kadar zor?
        - Bireysel öğrenci direkt satın alır (B2C) → 8-10
        - Öğretmen kanalıyla → 5-7
        - Müfredat entegrasyonu / yönetim onayı → 2-4

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7. Timing Score (Zamanlama) [1-10]
   → Google Trends puanı + sektördeki güncel gelişmeler

KURALLAR:
- Tüm fikirleri değerlendir, sadece iyileri seçme
- Medikal fikirde Regulatory Pathway 3 altındaysa analysis'te uyarı yaz
- Eğitim fikirinde pedagojik kanıt yoksa bunu açıkça belirt
- Analiz Türkçe yaz
- SADECE InvestmentMemo formatında şema döndür"""

    CRITIC_PROMPT_VERSION = "v2.1-health-education"
    
    registry = get_registry()
    active_prompt_obj = registry.get_active_prompt("critic") if registry else None

    if active_prompt_obj:
        is_outdated = not active_prompt_obj.notes or \
                      CRITIC_PROMPT_VERSION not in active_prompt_obj.notes
        if is_outdated:
            logger.info(f"[AGENT] Critic: Eski prompt güncelleniyor → {CRITIC_PROMPT_VERSION}")
            registry.register_prompt(
                "critic", fallback_prompt, status="active",
                notes=f"Health/Education domain-specific | {CRITIC_PROMPT_VERSION}"
            )
            system_prompt = fallback_prompt
        else:
            system_prompt = active_prompt_obj.content
            logger.info(f"[AGENT] Critic: Registry'den aktif prompt yüklendi ({CRITIC_PROMPT_VERSION})")
    else:
        system_prompt = fallback_prompt
        if registry:
            registry.register_prompt(
                "critic", fallback_prompt, status="active",
                notes=f"Health/Education domain-specific | {CRITIC_PROMPT_VERSION}"
            )

    from src.tools.gtrends_tools import get_trend_score
    
    user_content = "FİKİRLER HAVUZU:\n"
    for idea in ideas:
        # Fikrin ana konusu olarak ilk birkaç kelimesini veya başlığını kullan (Basit bir heuristic)
        trend_kw = " ".join(idea.title.split()[:2])
        trend_val = get_trend_score(trend_kw)
        idea.trend_score = trend_val
        
        user_content += f"\n- Fikir ID: {idea.idea_id}\n  Başlık: {idea.title}\n  Problem: {idea.problem}\n  Çözüm: {idea.solution}\n  Wedge: {idea.wedge}\n  Hedef Kitle: {idea.target_audience}\n  Google Trends Puanı (Zamanlama): {trend_val}/100\n"

    try:
        result = structured_llm.invoke(system_prompt + "\n\n" + user_content)
        
        if hasattr(result, 'usage_metadata') and result.usage_metadata:
             logger.debug(f"[Critic] Token -> Input: {result.usage_metadata.input_tokens}, Output: {result.usage_metadata.output_tokens}")
             
        logger.info(f"[AGENT] Critic: {len(result.evaluations)} fikir detaylandırıldı.")
        
        # Sadece toplam skoru belli bir eşiğin üstünde olanları (deterministic olarak) filtrelemek isteyebiliriz.
        # Supervisor aşamasında da yapılabilir. Şimdilik hepsini döndürüyoruz.
        return {"evaluations": result.evaluations}
    except Exception as e:
        logger.error(f"[AGENT] Critic Hatası: {e}")
        return {"evaluations": []}
