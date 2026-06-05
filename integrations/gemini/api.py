import logging

import google.generativeai as genai
from decouple import config

logger = logging.getLogger(__name__)

genai.configure(api_key=config('GEMINI_API_KEY'))

CAFE_REVIEW_PROMPT = """你是一位咖啡店評論專家。請根據以下資訊對這間咖啡店進行評價，
包含氛圍、適合族群、是否適合工作或讀書。

咖啡店名稱：{name}
地址：{address}
Google 評分：{rating}（{user_ratings_total} 則評論）

請用繁體中文回答，150 字以內。"""


class GeminiAPI:

    @staticmethod
    def review_cafe(name: str, address: str, rating: float, user_ratings_total: int) -> str | None:
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            prompt = CAFE_REVIEW_PROMPT.format(
                name=name,
                address=address,
                rating=rating or '無資料',
                user_ratings_total=user_ratings_total or 0,
            )
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f'Gemini API 呼叫失敗: {e}', exc_info=True)
            return None
