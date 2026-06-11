from pydantic import BaseModel


class ProductInfo(BaseModel):
    """Продукт из базы штрих-кодов (OpenFoodFacts). КБЖУ на 100 г.

    calories_100g=None — продукт найден, но КБЖУ в базе не заполнены
    (частый случай): берём название и оцениваем через LLM.
    """

    barcode: str
    name: str
    calories_100g: float | None = None
    protein_100g: float = 0
    fat_100g: float = 0
    carbs_100g: float = 0
    package_grams: float | None = None  # вес упаковки из карточки товара
