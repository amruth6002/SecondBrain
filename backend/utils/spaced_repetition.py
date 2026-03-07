"""SM-2 Spaced Repetition Algorithm implementation.

Based on Piotr Wozniak's SuperMemo-2 algorithm (1987).
Proven to improve retention by 200-400% over traditional review methods.
"""

from datetime import datetime, timedelta


def calculate_next_review(
    quality: int,
    easiness_factor: float = 2.5,
    interval: int = 1,
    repetitions: int = 0,
) -> dict:
    """Calculate the next review date using the SM-2 algorithm.

    Args:
        quality: User's self-assessed quality of recall (0-5)
            0 = complete blackout
            1 = incorrect, but recognized on reveal
            2 = incorrect, but easy to recall on reveal
            3 = correct with serious difficulty
            4 = correct with some hesitation
            5 = perfect recall
        easiness_factor: Current easiness factor (min 1.3)
        interval: Current interval in days
        repetitions: Number of successful repetitions

    Returns:
        Dict with updated easiness_factor, interval, repetitions, next_review
    """
    # Map our Easy/Medium/Hard to SM-2 quality scores
    # quality is already 0-5, but we also accept string mappings
    if isinstance(quality, str):
        quality_map = {"easy": 5, "medium": 3, "hard": 1}
        quality = quality_map.get(quality.lower(), 3)

    # Ensure quality is in range
    quality = max(0, min(5, quality))

    # Update easiness factor
    new_ef = easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)  # EF should never go below 1.3

    if quality >= 3:
        # Successful recall
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval * new_ef)
        new_repetitions = repetitions + 1
    else:
        # Failed recall — reset
        new_interval = 1
        new_repetitions = 0

    next_review_date = datetime.now() + timedelta(days=new_interval)

    return {
        "easiness_factor": round(new_ef, 2),
        "interval": new_interval,
        "repetitions": new_repetitions,
        "next_review": next_review_date.isoformat(),
    }
