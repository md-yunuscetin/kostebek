# scripts/check_env.py

import os
from dotenv import load_dotenv

def check_env():
    load_dotenv()
    
    required_vars = [
        "GEMINI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID"
    ]
    
    optional_vars = [
        "REDIS_URL",
        "PRAW_CLIENT_ID",
        "PRAW_CLIENT_SECRET",
        "LANGCHAIN_API_KEY"
    ]
    
    print("🔍 Ortam Değişkenleri Kontrol Ediliyor...\n")
    
    missing_required = []
    for var in required_vars:
        val = os.getenv(var)
        if not val:
            missing_required.append(var)
            print(f"❌ {var}: EKSİK (Kritik)")
        else:
            masked = val[:4] + "*" * (len(val) - 8) + val[-4:] if len(val) > 8 else "****"
            print(f"✅ {var}: Ayarlı ({masked})")
            
    print("\n--- Opsiyonel Değişkenler ---\n")
    for var in optional_vars:
        val = os.getenv(var)
        if not val:
            print(f"⚠️ {var}: Ayarlı Değil (Varsayılan veya fallback kullanılacak)")
        else:
            print(f"✅ {var}: Ayarlı")
            
    if missing_required:
        print(f"\n❌ HATA: {len(missing_required)} kritik değişken eksik! Pipeline düzgün çalışmayabilir.")
        exit(1)
    else:
        print("\n🚀 Tüm kritik değişkenler hazır. Bulut kurulumuna uygun.")

if __name__ == "__main__":
    check_env()
