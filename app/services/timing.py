import random

def reply_wait(started_at, now, minimum, maximum, rng=random.uniform):
    target=rng(minimum, maximum)
    return max(0.0, target-(now-started_at))
