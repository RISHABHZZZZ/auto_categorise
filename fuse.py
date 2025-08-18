# fuse.py
def fuse_scores(s1: float, s2: float, s3: float, w=(0.20, 0.35, 0.45)) -> float:
    a, b, c = w
    score = a*s1 + b*s2 + c*s3
    return max(0.0, min(1.0, score))
