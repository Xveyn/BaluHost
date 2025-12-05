from functools import lru_cache
from typing import Dict

# Beispiel: Simulierte DB-Abfrage

def fetch_metadata_from_db(user_id: int) -> Dict:
    # Hier würde die echte DB-Abfrage stehen
    return {"user_id": user_id, "name": f"User{user_id}", "role": "user"}

@lru_cache(maxsize=128)
def get_user_metadata(user_id: int) -> Dict:
    """
    Holt und cached User-Metadaten für Performance-Optimierung.
    """
    return fetch_metadata_from_db(user_id)
