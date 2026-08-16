import logging
import requests
from datetime import date
from typing import Union
from decouple import config

from line_bot.utils import parse_opening_hours

from cafe.tasks import download_and_upload_cafe_photo
from cafe.models import Cafe

logger = logging.getLogger(__name__)


class FlexMessageBuilder:
    WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    CLOSED_TEXTS = {'休息', '公休', 'Closed'}
    DEFAULT_PHOTO_URL = 'https://developers.line.biz/assets/images/services/bot-designer-icon.png'
    # 標籤樣式配置
    TAG_STYLES = {
        'socket': {
            'color': '#0F5132',
            'backgroundColor': '#D1E7DD',
        },
        'limited_time': {
            'color': '#055160',
            'backgroundColor': '#CFF4FC',
        },
        'has_pet': {
            'color': '#6B3A2A',
            'backgroundColor': '#F5E6D3',
        },
        'pet_friendly': {
            'color': '#5C4B00',
            'backgroundColor': '#FFF3CD',
        },
    }

    @staticmethod
    def get_photo_url(cafe_dict_or_obj, allow_sync_resolve=True):
        """
        取得照片 URL 的優先順序：
        1. S3 URL -> 若已經查詢過會異步存到 S3，再從 S3 抓下來
        2. resolve Google Photo URL -> 透過 photo_reference 去抓取實際的圖片 url（僅限第一次，且 allow_sync_resolve 為 True 時才會同步嘗試）
        3. 預設圖 -> 若沒有設定 photo_reference，或 allow_sync_resolve 為 False，給預設圖

        Args:
            cafe_dict_or_obj: dict 或 Cafe model 物件
            allow_sync_resolve: 是否允許同步呼叫 Google Photo API 解析（單筆結果可等待，多筆結果應設為 False 避免逐間阻塞）

        Returns:
            str: 照片 URL
        """

        if not isinstance(cafe_dict_or_obj, dict):
            # 如果是 Cafe 物件，轉換為字典以統一處理
            cafe_dict_or_obj = cafe_dict_or_obj.to_dict()

        photo_s3_url = cafe_dict_or_obj.get('photo_s3_url', '')
        photo_reference = cafe_dict_or_obj.get('photo_reference', '')
        place_id = cafe_dict_or_obj.get('place_id', '')

        if photo_s3_url:
            logger.info(f'place_id: {place_id}, photo_s3_url: {photo_s3_url}，從S3 拉資料')
            return photo_s3_url


        elif photo_reference:
            if allow_sync_resolve:
                logger.info(f'place_id: {place_id}, photo_reference: {photo_reference}，解析google photo')
                resolved_url = FlexMessageBuilder.resolve_photo_url(photo_reference)
            else:
                resolved_url = FlexMessageBuilder.DEFAULT_PHOTO_URL

            # 背景快取觸發與同步解析是否嘗試、是否成功無關，只要有 photo_reference 且尚未快取即觸發
            FlexMessageBuilder._trigger_s3_upload(place_id)

            return resolved_url

        else:
            logger.info(f'place_id: {place_id}，因沒有設定圖片，使用預設圖')
            return FlexMessageBuilder.DEFAULT_PHOTO_URL

    @staticmethod
    def _trigger_s3_upload(place_id: str):
        """
        觸發背景任務上傳照片到 S3

        這是異步任務，不會阻塞主流程

        Args:
            place_id: Google Places ID
        """
        try:
            # 取得 cafe 物件
            cafe = Cafe.objects.filter(place_id=place_id).first()
            if cafe and not cafe.photo_s3_url:
                logger.info(f'觸發背景任務：上傳照片到 S3 - {place_id}')
                result = download_and_upload_cafe_photo.delay(cafe.id)
                logger.warning(f'Celery task sent: {result.id}')
            else:
                logger.debug('跳過背景任務（已有 S3 URL 或找不到 cafe）')
        except Exception as e:
            logger.error(f'觸發背景任務失敗: {e}')

    @staticmethod
    def resolve_photo_url(photo_reference: str) -> str:
        """解析 Google Places Photo API 重導向，取得實際圖片 URL"""
        if not photo_reference:
            return FlexMessageBuilder.DEFAULT_PHOTO_URL

        photo_api_url = (
            f'https://maps.googleapis.com/maps/api/place/photo'
            f'?photo_reference={photo_reference}'
            f'&maxwidth=400'
            f'&key={config("GOOGLE_API_KEY")}'
        )

        try:
            response = requests.head(photo_api_url, allow_redirects=True, timeout=2)
            if response.status_code == 200:
                return response.url
        except requests.RequestException as e:
            logger.warning(f'解析 Google photo URL 失敗 (reference: {photo_reference}): {e}')
        return FlexMessageBuilder.DEFAULT_PHOTO_URL

    @staticmethod
    def _create_attribute_tags(info: dict) -> list:
        """
        根據咖啡店屬性生成標籤列表，抓是否有插座 跟 限時資訊

        Args:
            info: 包含 has_socket 和 limited_time 的字典

        Returns:
            list: 標籤元素列表，可能為空
        """
        tags = []

        # 插座標籤：yes/maybe 顯示，no 不顯示
        has_socket = info.get('has_socket')
        if has_socket in ('yes', 'maybe'):
            tags.append(FlexMessageBuilder._create_tag_element(
                text='🔌 有插座',
                tag_type='socket'
            ))

        # 店家是否有貓貓狗狗：yes/maybe 顯示，no 不顯示
        has_pet = info.get('has_pet')
        if has_pet in ('yes', 'maybe'):
            tags.append(FlexMessageBuilder._create_tag_element(
                text='🐈 有貓貓狗狗',
                tag_type='has_pet'
            ))

        # 店家是否為寵物友善：yes/maybe 顯示，no 不顯示
        pet_friendly = info.get('pet_friendly')
        if pet_friendly in ('yes', 'maybe'):
            tags.append(FlexMessageBuilder._create_tag_element(
                text='🐕 寵物友善',
                tag_type='pet_friendly'
            ))

        # 限時標籤：根據值顯示不同文字
        limited_time = info.get('limited_time')
        limited_time_text_map = {
            'no': '⏱ 不限時',
            'maybe': '⏱ 視情況',
            'yes': '⏱ 有限時',
        }
        limited_time_text = limited_time_text_map.get(limited_time)

        if limited_time_text:
            tags.append(FlexMessageBuilder._create_tag_element(
                text=limited_time_text,
                tag_type='limited_time'
            ))

        return tags

    @staticmethod
    def _create_tag_element(text: str, tag_type: str) -> dict:
        """
        創建單個標籤元素

        Args:
            text: 標籤文字
            tag_type: 標籤類型 ('socket','limited_time','has_pet','pet_friendly')

        Returns:
            dict: Flex Message text element
        """
        style = FlexMessageBuilder.TAG_STYLES.get(tag_type, {})
        return {
            'type': 'text',
            'text': text,
            'size': 'xs',
            'color': style.get('color', '#666666'),
            'backgroundColor': style.get('backgroundColor', '#EEEEEE'),
            'paddingStart': '8px',
            'paddingEnd': '8px',
            'paddingTop': '4px',
            'paddingBottom': '4px',
            'cornerRadius': '12px',
            'flex': 0
        }

    @staticmethod
    def _create_tags_box(tags: list) -> dict:
        """
        創建標籤容器 box。
        當標籤數量小於或等於每列最大限制時，使用單一水平列顯示；
        當標籤數量超過限制時，自動分成多列並以垂直 box 包裹。

        Args:
            tags: 標籤元素列表，呼叫端須確保非空

        Returns:
            dict: Flex Message box 元素
        """
        max_tags_per_row = 2
        if len(tags) <= max_tags_per_row:
            return {
                'type': 'box',
                'layout': 'horizontal',
                'spacing': 'sm',
                'margin': 'md',
                'contents': tags
            }
        rows = [tags[i:i + max_tags_per_row] for i in range(0, len(tags), max_tags_per_row)]
        row_boxes = [
            {'type': 'box', 'layout': 'horizontal', 'spacing': 'sm', 'contents': row}
            for row in rows
        ]
        return {
            'type': 'box',
            'layout': 'vertical',
            'spacing': 'sm',
            'margin': 'md',
            'contents': row_boxes
        }

    # 處理營業時間格式
    @staticmethod
    def format_opening_hours(open_hours: Union[dict, list]):
        """將營業時間列表格式化為簡潔字串"""

        if not open_hours:
            return '營業時間未提供'

        """
        1. 從資料庫拉出來的營業時間範例：-> dict
        'opening_hours':
        {'星期一: 12:00 – 00:00', '星期二: 12:00 – 00:00', '星期四: 12:00 – 00:00', '星期五: 12:00 – 00:00', '星期六: 12:00 – 00:00', '星期日: 12:00 – 00:00'}

        2. 從 Google API 拉出來的營業時間範例： -> list
        ['星期一: 12:00 – 20:00', '星期二: 12:00 – 20:00', '星期三: 12:00 – 20:00', '星期四: 12:00 – 20:00', '星期五: 12:00 – 20:00', '星期六: 12:00 – 20:00', '星期日: 12:00 – 20:00']
        """

        if isinstance(open_hours, dict):
            hours_d = open_hours

        else:
            # 處理從 Google API 拉出來的 list 格式
            hours_d = parse_opening_hours(open_hours)

        # 星期對應表
        weekday_index = date.today().isoweekday() - 1  # 轉成 0～6
        today = FlexMessageBuilder.WEEKDAYS[weekday_index]

        if today in hours_d:
            time_str = hours_d[today]
            # 如果是「休息」或「公休」，明確顯示
            if time_str in FlexMessageBuilder.CLOSED_TEXTS:
                return '今日休息'
            return time_str
        return '今日未營業'

    @staticmethod
    def create_shop_flex_message(info, is_multiple=False):

        def _generate_star_icons(rating):
            """根據評分生成星星圖示"""
            if not rating:
                return []

            stars = []
            full_stars = int(rating)  # 整數部分
            has_half_star = (rating - full_stars) >= 0.3  # 0.3以上顯示半星

            # 添加滿星
            for _ in range(full_stars):
                stars.append({
                    'type': 'icon',
                    'size': 'sm',
                    'url': 'https://developers-resource.landpress.line.me/fx/img/review_gold_star_28.png'
                })

            # 添加半星
            if has_half_star and full_stars < 5:
                stars.append({
                    'type': 'icon',
                    'size': 'sm',
                    'url': 'https://developers-resource.landpress.line.me/fx/img/review_gold_star_28.png'
                })
                full_stars += 1

            # 填充灰星到5顆
            for _ in range(5 - full_stars):
                stars.append({
                    'type': 'icon',
                    'size': 'sm',
                    'url': 'https://developers-resource.landpress.line.me/fx/img/review_gray_star_28.png'
                })

            return stars

        # 建立星星評分區塊
        star_icons = _generate_star_icons(info.get('rating'))
        rating_box_contents = star_icons.copy()

        # 添加評分文字
        rating_text = f'{info.get('rating', 'N/A')}'
        if info.get('user_ratings_total'):
            rating_text += f' ({info.get('user_ratings_total')}則評論)'

        rating_box_contents.append({
            'type': 'text',
            'text': rating_text,
            'size': 'sm',
            'color': '#999999',
            'margin': 'md',
            'flex': 0
        })

        # 處理咖啡店照片
        photo_url = FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=not is_multiple)

        # 建立 Flex Message
        flex_message = {
            'type': 'bubble',
            'hero': {
                'type': 'image',
                'url': photo_url,
                'size': 'full',
                'aspectRatio': '20:13',
                'aspectMode': 'cover',
                'action': {
                    'type': 'uri',
                    'uri': info.get('google_maps', 'https://line.me/')
                }
            },
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {
                        'type': 'text',
                        'text': info.get('name', '店家名稱未提供'),
                        'weight': 'bold',
                        'size': 'xl',
                        'wrap': True
                    },
                    {
                        'type': 'box',
                        'layout': 'baseline',
                        'margin': 'md',
                        'contents': rating_box_contents
                    },
                    {
                        'type': 'box',
                        'layout': 'vertical',
                        'margin': 'lg',
                        'spacing': 'sm',
                        'contents': [
                            {
                                'type': 'box',
                                'layout': 'baseline',
                                'spacing': 'sm',
                                'contents': [
                                    {
                                        'type': 'text',
                                        'text': '📍 地址',
                                        'color': '#aaaaaa',
                                        'size': 'sm',
                                        'flex': 2
                                    },
                                    {
                                        'type': 'text',
                                        'text': info.get('address', '地址未提供'),
                                        'wrap': True,
                                        'color': '#666666',
                                        'size': 'sm',
                                        'flex': 5
                                    }
                                ]
                            },
                            {
                                'type': 'box',
                                'layout': 'baseline',
                                'spacing': 'sm',
                                'contents': [
                                    {
                                        'type': 'text',
                                        'text': '📞 電話',
                                        'color': '#aaaaaa',
                                        'size': 'sm',
                                        'flex': 2
                                    },
                                    {
                                        'type': 'text',
                                        'text': info.get('phone', '電話未提供'),
                                        'wrap': True,
                                        'color': '#666666',
                                        'size': 'sm',
                                        'flex': 5
                                    }
                                ]
                            },
                            {
                                'type': 'box',
                                'layout': 'baseline',
                                'spacing': 'sm',
                                'contents': [
                                    {
                                        'type': 'text',
                                        'text': '⏰ 營業',
                                        'color': '#aaaaaa',
                                        'size': 'sm',
                                        'flex': 2
                                    },
                                    {
                                        'type': 'text',
                                        'text': FlexMessageBuilder.format_opening_hours(info.get('opening_hours', {})),
                                        'wrap': True,
                                        'color': '#666666',
                                        'size': 'sm',
                                        'flex': 5
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            'footer': {
                'type': 'box',
                'layout': 'horizontal',
                'spacing': 'sm',
                'contents': []
            }
        }

        # 插入屬性標籤（在評分之後、詳細資訊之前）
        attribute_tags = FlexMessageBuilder._create_attribute_tags(info)
        if attribute_tags:
            tags_box = FlexMessageBuilder._create_tags_box(attribute_tags)
            # 插入到 body contents 的第三個位置（店名、評分之後）
            flex_message['body']['contents'].insert(2, tags_box)

        if is_multiple:
            # 多筆結果時：顯示「看地圖」與「選擇這間」
            flex_message['footer']['contents'].extend([
                {
                    'type': 'button',
                    'style': 'link',
                    'action': {
                        'type': 'uri',
                        'label': '看地圖 ',
                        'uri': info.get('google_maps', 'https://maps.google.com/')
                    }
                },
                {
                    'type': 'button',
                    'style': 'link',
                    'action': {
                        'type': 'postback',
                        'label': '選擇這間',
                        'data': f'action=view_detail&place_id={info.get("place_id")}',
                    }
                }
            ])
        else:
            # 單筆結果時：顯示「看地圖」與「官方網站」
            flex_message['footer']['contents'].append({
                'type': 'button',
                'style': 'primary',
                'action': {
                    'type': 'uri',
                    'label': '看地圖',
                    'uri': info.get('google_maps', 'https://maps.google.com/')
                }
            })
            if info.get('website') and info.get('website') != '無提供':
                flex_message['footer']['contents'].append({
                    'type': 'button',
                    'style': 'link',
                    'action': {
                        'type': 'uri',
                        'label': '官方網站',
                        'uri': info.get('website')
                    }
                })

        return flex_message
