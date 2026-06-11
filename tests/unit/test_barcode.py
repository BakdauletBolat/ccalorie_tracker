from app.clients.openfoodfacts import parse_product
from app.models import ProductInfo
from app.services import BarcodeService

BARCODE = "4870001234560"


def _off_response(**product_overrides) -> dict:
    product = {
        "product_name": "Греческий йогурт",
        "brands": "Epica",
        "nutriments": {
            "energy-kcal_100g": 59,
            "proteins_100g": 10,
            "fat_100g": 1.5,
            "carbohydrates_100g": 3.6,
        },
        "product_quantity": "130",
        "product_quantity_unit": "g",
    }
    product.update(product_overrides)
    return {"status": 1, "product": product}


# ── parse_product ────────────────────────────────────────


def test_parse_product_full():
    info = parse_product(BARCODE, _off_response())
    assert info is not None
    assert info.name == "Греческий йогурт (Epica)"
    assert info.calories_100g == 59
    assert info.protein_100g == 10
    assert info.package_grams == 130


def test_parse_product_not_found():
    assert parse_product(BARCODE, {"status": 0}) is None


def test_parse_product_no_nutrition_keeps_name():
    """Продукт без КБЖУ (как Sprite 54491069): имя и вес сохраняем, calories=None."""
    info = parse_product(BARCODE, _off_response(nutriments={}))
    assert info is not None
    assert info.calories_100g is None
    assert info.name == "Греческий йогурт (Epica)"
    assert info.package_grams == 130


def test_parse_product_kj_fallback():
    info = parse_product(BARCODE, _off_response(nutriments={"energy_100g": 418.4, "proteins_100g": 5}))
    assert info is not None
    assert abs(info.calories_100g - 100) < 0.01  # 418.4 кДж = 100 ккал


def test_parse_product_no_quantity():
    info = parse_product(BARCODE, _off_response(product_quantity=None))
    assert info is not None
    assert info.package_grams is None


def test_parse_product_bad_quantity():
    info = parse_product(BARCODE, _off_response(product_quantity="примерно 130"))
    assert info is not None
    assert info.package_grams is None


def test_parse_product_brand_already_in_name():
    info = parse_product(BARCODE, _off_response(product_name="Epica йогурт"))
    assert info is not None
    assert info.name == "Epica йогурт"  # бренд не дублируется


# ── to_product_item ──────────────────────────────────────


def test_to_product_item_scales_nutrition():
    info = ProductInfo(
        barcode=BARCODE, name="Йогурт",
        calories_100g=59, protein_100g=10, fat_100g=1.5, carbs_100g=3.6,
    )
    item = BarcodeService.to_product_item(info, 200)
    assert item.grams == 200
    assert item.nutrition.calories == 118
    assert item.nutrition.protein == 20
    assert item.short_description == "Йогурт"
    assert "200г" in item.description


# ── lookup с кэшем ───────────────────────────────────────


class FakeProductCache:
    def __init__(self) -> None:
        self._items: dict[str, ProductInfo] = {}

    async def get(self, barcode: str) -> ProductInfo | None:
        return self._items.get(barcode)

    async def set(self, info: ProductInfo) -> None:
        self._items[info.barcode] = info


class FakeOFFClient:
    def __init__(self, info: ProductInfo | None) -> None:
        self._info = info
        self.calls = 0

    async def fetch(self, barcode: str) -> ProductInfo | None:
        self.calls += 1
        return self._info


async def test_lookup_caches_result():
    info = ProductInfo(barcode=BARCODE, name="Йогурт", calories_100g=59,
                       protein_100g=10, fat_100g=1.5, carbs_100g=3.6)
    client = FakeOFFClient(info)
    svc = BarcodeService(client, FakeProductCache())  # type: ignore[arg-type]

    assert await svc.lookup(BARCODE) is not None
    assert await svc.lookup(BARCODE) is not None
    assert client.calls == 1  # второй раз — из кэша


async def test_lookup_miss_not_cached():
    client = FakeOFFClient(None)
    svc = BarcodeService(client, FakeProductCache())  # type: ignore[arg-type]

    assert await svc.lookup(BARCODE) is None
    assert await svc.lookup(BARCODE) is None
    assert client.calls == 2  # промахи не кэшируются


async def test_lookup_no_nutrition_not_cached():
    """Карточку без КБЖУ не кэшируем — в OFF её могут дозаполнить."""
    info = ProductInfo(barcode=BARCODE, name="Sprite")
    client = FakeOFFClient(info)
    svc = BarcodeService(client, FakeProductCache())  # type: ignore[arg-type]

    result = await svc.lookup(BARCODE)
    assert result is not None and result.calories_100g is None
    await svc.lookup(BARCODE)
    assert client.calls == 2


# ── decode ───────────────────────────────────────────────


def test_decode_roundtrip():
    import io

    import zxingcpp
    from PIL import Image

    bc = zxingcpp.create_barcode(BARCODE, zxingcpp.BarcodeFormat.EAN13)
    img = zxingcpp.write_barcode_to_image(bc)
    height, width = img.shape
    pil = Image.frombuffer("L", (width, height), img, "raw", "L", 0, 1)
    buf = io.BytesIO()
    pil.convert("RGB").save(buf, format="JPEG")

    assert BarcodeService.decode(buf.getvalue()) == BARCODE


def test_decode_no_barcode():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(buf, format="JPEG")
    assert BarcodeService.decode(buf.getvalue()) is None


def test_decode_garbage_bytes():
    assert BarcodeService.decode(b"not an image") is None
