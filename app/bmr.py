def calc_bmr(weight: float, height: float, age: int, gender: str) -> float:
    """Формула Миффлина-Сан Жеора (2005)."""
    base = 10 * weight + 6.25 * height - 5 * age
    if gender == "male":
        return base + 5
    return base - 161
