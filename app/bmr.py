ACTIVITY_COEFFICIENT = 1.2  # сидячий образ жизни


def calc_bmr(weight: float, height: float, age: int, gender: str) -> float:
    """Формула Миффлина-Сан Жеора (2005) × коэффициент активности."""
    base = 10 * weight + 6.25 * height - 5 * age
    if gender == "male":
        bmr = base + 5
    else:
        bmr = base - 161
    return bmr * ACTIVITY_COEFFICIENT
