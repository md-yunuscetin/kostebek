import yaml

def load_config(path: str = "config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Uyarı: {path} dosyası bulunamadı. Lütfen config.yaml dosyasını kontrol edin.")
        return {}

config = load_config()
