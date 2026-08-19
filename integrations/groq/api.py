import logging

from groq import Groq
from decouple import config

logger = logging.getLogger(__name__)

CAFE_REVIEW_PROMPT = """你是一位咖啡店評論專家。請根據以下資訊對這間咖啡店進行說明，
包含氛圍、適合族群、是否適合工作或讀書，還有該店推薦的商品。

咖啡店名稱：{name}
地址：{address}
Google 評分：{rating}（{user_ratings_total} 則評論）
用戶評論：
{reviews}

請用繁體中文回答，150 字以內。"""


class GroqAPI:
    _client = None

    @classmethod
    def review_cafe(cls, name: str, address: str, rating: float, user_ratings_total: int, reviews: list) -> str | None:
        try:
            if cls._client is None:
                cls._client = Groq(api_key=config('GROQ_API_KEY'))
            reviews_text = '\n'.join(f'- {r}' for r in reviews) if reviews else '無用戶評論'
            prompt = CAFE_REVIEW_PROMPT.format(
                name=name,
                address=address,
                rating=rating if rating is not None else '無資料',
                user_ratings_total=user_ratings_total if user_ratings_total is not None else 0,
                reviews=reviews_text,
            )
            response = cls._client.chat.completions.create(
                model='openai/gpt-oss-20b',
                messages=[{'role': 'user', 'content': prompt}],
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f'Groq API 呼叫失敗: {e}', exc_info=True)
            return None
