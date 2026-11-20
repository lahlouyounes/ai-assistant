"""Limitation de débit en mémoire : fenêtre glissante par IP + plafond quotidien global (protège votre facture)."""
import threading
import time
from collections import defaultdict, deque

from .config import settings


class Limiter:
    def __init__(self):
        self.hits = defaultdict(deque)
        self.day = time.strftime("%Y-%m-%d")
        self.count = 0
        self.lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, str]:
        now = time.time()
        with self.lock:
            today = time.strftime("%Y-%m-%d")
            if today != self.day:
                self.day, self.count = today, 0
            if settings.daily_cap and self.count >= settings.daily_cap:
                return False, "Limite quotidienne du service atteinte. Réessayez demain."
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if settings.rate_limit_per_min and len(q) >= settings.rate_limit_per_min:
                return False, "Trop de requêtes. Patientez une minute."
            q.append(now)
            self.count += 1
            if len(self.hits) > 10000:  # évite la croissance mémoire
                self.hits = defaultdict(deque, {k: v for k, v in self.hits.items() if v and now - v[-1] <= 60})
            return True, ""


limiter = Limiter()
