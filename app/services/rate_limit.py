import time
from collections import defaultdict, deque
class RateLimiter:
    def __init__(self, limit, window): self.limit=limit; self.window=window; self.events=defaultdict(deque); self.notified=set()
    def allow(self, user_id):
        now=time.monotonic(); q=self.events[user_id]
        while q and now-q[0]>self.window: q.popleft()
        if len(q)>=self.limit: return False, user_id not in self.notified
        q.append(now); self.notified.discard(user_id); return True, False
    def mark_notified(self,user_id): self.notified.add(user_id)

