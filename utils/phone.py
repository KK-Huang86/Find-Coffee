import re
import unicodedata

# 電話分機標記，標記之後的內容不併入撥號號碼
PHONE_EXTENSION_PATTERN = re.compile(r'#|分機|ext|轉|,|;', re.IGNORECASE)
# 撥號號碼位數範圍（上限依 E.164）
PHONE_MIN_DIGITS = 3
PHONE_MAX_DIGITS = 15


def build_tel_uri(phone) -> str | None:
    """
    將店家電話正規化為 tel: URI，供 LINE 撥號按鈕與咖啡地圖共用

    Args:
        phone: 店家電話字串，例如 '02 2345 6789'

    Returns:
        str | None: 例如 'tel:0223456789'；電話缺失或格式不合法時回傳 None
    """
    if not isinstance(phone, str):
        return None

    # 全形數字、符號轉半形，並截斷分機
    normalized = unicodedata.normalize('NFKC', phone).strip()
    normalized = PHONE_EXTENSION_PATTERN.split(normalized, maxsplit=1)[0]

    digits = re.sub(r'\D', '', normalized)
    if not PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS:
        return None

    prefix = '+' if normalized.startswith('+') else ''
    return f'tel:{prefix}{digits}'
