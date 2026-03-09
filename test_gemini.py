import os
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("GEMINI_API_KEY")
if not key:
    print("❌ Error: GEMINI_API_KEY not found in .env")
    exit(1)

keys = [key]
models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

print(f"\n--- Testing with key from .env: {key[:10]}... ---")
    for model_name in models:
        print(f"Testing model: {model_name}...", end=" ", flush=True)
        try:
            llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
            response = llm.invoke("Hi")
            print("✅ SUCCESS")
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                print("❌ 429 RATE LIMIT")
            elif "404" in err_str or "NOT_FOUND" in err_str:
                print("❌ 404 NOT FOUND")
            elif "API_KEY_INVALID" in err_str:
                print("❌ INVALID KEY")
            else:
                print(f"❌ ERROR: {err_str[:100]}")
