# src/agents/domain_filter.py
# Bu node, Extractor'dan gelen pain_points'leri domain kısıtına göre filtreler.
# Alakasız pain_points → elenir, pipeline devam etmez.

from src.state import AgentState
from src.utils.logger import get_logger

logger = get_logger("domain_filter")

# ──────────────────────────────────────────────
# ALAN TANIMLAMALARI — Buraya istediğin alanı ekle/çıkar
# ──────────────────────────────────────────────
ALLOWED_DOMAINS = {
    "tıp_klinik": [
        "diagnosis", "treatment", "clinical", "patient", "hospital", "physician",
        "EHR", "EMR", "radiology", "pathology", "surgery", "teşhis", "tedavi",
        "hasta", "klinik", "doktor", "muayene", "ilaç", "reçete", "laboratuvar",
        "görüntüleme", "MRI", "CT", "ultrason", "hemşire", "poliklinik", "acil",
        "ameliyat", "kanser", "diyabet", "kardiyoloji", "nöroloji", "pediatri",
        "psikiyatri", "ortopedi", "dermatoloji", "tıbbi", "sağlık bakımı",
        "chronic disease", "telemedicine", "telehealth", "remote patient"
    ],
    "sağlık_teknolojisi": [
        "healthtech", "digital health", "wearable", "medical device", "biosensor",
        "health app", "FDA", "CE marking", "HIPAA", "HL7", "FHIR", "medical AI",
        "dijital sağlık", "sağlık teknolojisi", "medikal", "biyomedikal",
        "health monitoring", "vital signs", "glucose", "blood pressure",
        "mental health", "ruh sağlığı", "psikoloji", "terapi", "wellness",
        "ilaç geliştirme", "klinik araştırma", "clinical trial", "drug discovery"
    ],
    "tıp_eğitimi": [
        "medical education", "medical school", "residency", "USMLE", "MCAT",
        "clinical simulation", "anatomy", "pharmacology", "pathophysiology",
        "TUS", "tıp fakültesi", "tıp öğrencisi", "uzmanlık", "asistan",
        "tıp eğitimi", "klinik simülasyon", "anatomi", "farmakoloji",
        "fizyoloji", "histoloji", "biyokimya", "mikrobiyoloji", "parazitoloji",
        "dahiliye", "pediatri eğitimi", "cerrahi eğitimi"
    ],
    "halk_sağlığı": [
        "public health", "epidemiology", "vaccination", "outbreak", "pandemic",
        "chronic disease", "prevention", "WHO", "CDC", "population health",
        "halk sağlığı", "epidemiyoloji", "aşı", "koruyucu sağlık", "salgın",
        "bulaşıcı hastalık", "beslenme", "obezite", "sağlık politikası"
    ],
    "genel_eğitim": [
        "edtech", "e-learning", "LMS", "personalized learning", "curriculum",
        "assessment", "tutoring", "student", "teacher", "classroom",
        "eğitim", "öğrenme", "müfredat", "öğrenci", "öğretmen", "ders",
        "okul", "üniversite", "bootcamp", "sertifika", "online kurs",
        "adaptive learning", "gamification", "microlearning", "pedagoji"
    ]
}

# Her pain_point için minimum eşik — kaç keyword eşleşmesi gerekiyor?
MIN_KEYWORD_MATCH = 1  # Hassasiyeti artırmak için 2 yap


def _score_text(text: str) -> tuple[str, int]:
    """Metni tüm domain'lere karşı puanlar. En yüksek skoru ve domain'i döndürür."""
    text_lower = text.lower()
    best_domain = "kapsam_dışı"
    best_score = 0

    for domain, keywords in ALLOWED_DOMAINS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > best_score:
            best_score = score
            best_domain = domain

    return best_domain, best_score


def _extract_text(pain_point) -> str:
    """PainPoint dict, string veya object olabilir — metni güvenli şekilde çıkar."""
    if isinstance(pain_point, str):
        return pain_point
    if isinstance(pain_point, dict):
        # Yaygın field isimleri
        for field in ["description", "text", "content", "problem", "title", "summary"]:
            if field in pain_point and pain_point[field]:
                return str(pain_point[field])
        return str(pain_point)
    # Pydantic model veya dataclass olabilir
    for attr in ["description", "text", "content", "problem", "title", "summary"]:
        if hasattr(pain_point, attr):
            val = getattr(pain_point, attr)
            if val:
                return str(val)
    return str(pain_point)


def run_domain_filter_agent(state: AgentState) -> dict:
    """
    LangGraph Node: Extractor'dan gelen pain_points'leri filtreler.
    Yalnızca Tıp / Sağlık / Eğitim alanındaki pain_points'leri geçirir.
    """
    pain_points = state.get("pain_points", [])
    
    if not pain_points:
        logger.warning("[DOMAIN_FILTER] Filtrelenecek pain_point yok.")
        return {"pain_points": []}

    logger.info(f"[DOMAIN_FILTER] {len(pain_points)} pain_point filtreleniyor...")

    approved = []
    rejected = []

    for pp in pain_points:
        text = _extract_text(pp)
        domain, score = _score_text(text)

        if score >= MIN_KEYWORD_MATCH:
            approved.append(pp)
            logger.info(f"  ✅ KABUL | Domain: {domain} | Skor: {score} | {text[:70]}...")
        else:
            rejected.append(text[:70])
            logger.debug(f"  ❌ REDDEDİLDİ | Skor: {score} | {text[:70]}...")

    logger.info(
        f"[DOMAIN_FILTER] Sonuç → Kabul: {len(approved)} | Reddedildi: {len(rejected)} "
        f"| Oran: %{int(len(approved)/len(pain_points)*100) if pain_points else 0}"
    )

    if rejected:
        logger.debug(f"[DOMAIN_FILTER] Reddedilenler: {rejected}")

    return {"pain_points": approved}


def check_domain_filter_route(state: AgentState) -> str:
    """
    DomainFilter sonrası routing:
    - Geçerli pain_point varsa → IdeaGen
    - Hiç kalmadıysa → END (gereksiz LLM çağrısını engeller)
    """
    pain_points = state.get("pain_points", [])
    if not pain_points:
        logger.warning("[DOMAIN_FILTER] Filtreden geçen pain_point kalmadı → Pipeline sonlandırılıyor.")
        return "END"
    logger.info(f"[DOMAIN_FILTER] {len(pain_points)} geçerli pain_point → IdeaGen'e aktarılıyor.")
    return "IdeaGen"
