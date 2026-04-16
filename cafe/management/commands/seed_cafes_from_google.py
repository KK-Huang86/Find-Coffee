"""
從個人 Google Maps 清單種入咖啡店資料

使用方式：
    # Step 1：從 Google Maps 清單 URL 擷取 place_ids（需要 Playwright）
    uv run python manage.py seed_cafes_from_google --url "https://www.google.com/maps/..."

    # Step 2：從已儲存的 JSON 檔讀取
    uv run python manage.py seed_cafes_from_google --file place_ids.json

    # 直接傳入 place_id
    uv run python manage.py seed_cafes_from_google --ids ChIJabc123 ChIJdef456

    # 試跑（不寫入 DB）
    uv run python manage.py seed_cafes_from_google --url "..." --dry-run

place_ids.json 格式：
    ["ChIJ001", "ChIJ002", ...]
"""

import json
import re
import time
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from cafe.models import Cafe, CafeAttributeVote
from integrations.google.api import GoogleAPI
from line_bot.utils import parse_opening_hours

logger = logging.getLogger(__name__)

# 種入時預設的屬性值（來自手動整理的清單，已知有插座、不確定是否限時）
SEED_SOCKET_VALUE = 'yes'
SEED_LIMITED_TIME_VALUE = 'maybe'


class Command(BaseCommand):
    help = '從個人 Google Maps 清單批次匯入咖啡店資料（照片延遲到使用者查詢時再抓）'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--url',
            type=str,
            help='Google Maps 清單 URL，用 Playwright 擷取所有 place_id',
        )
        group.add_argument(
            '--file',
            type=str,
            help='JSON 檔路徑，內容為 place_id 陣列，例如 place_ids.json',
        )
        group.add_argument(
            '--ids',
            nargs='+',
            type=str,
            help='直接輸入 place_id，可多個，空格分隔',
        )

        parser.add_argument(
            '--save-ids',
            type=str,
            metavar='FILE',
            help='搭配 --url 使用，將擷取到的 place_ids 另存為 JSON 檔（方便下次複用）',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='模擬執行：顯示會做什麼，但不實際寫入 DB',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.5,
            help='每次 Details API 呼叫之間的間隔秒數（預設 0.5 秒）',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        delay = options['delay']

        # ── Step 0：取得 place_id 清單 ──────────────────────────────────────
        place_ids = self._load_place_ids(options)

        if not place_ids:
            raise CommandError('找不到任何 place_id，請確認輸入')

        self.stdout.write(f'\n共 {len(place_ids)} 個 place_id 待處理')
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  dry-run 模式，不會寫入 DB\n'))

        # ── Step 1：逐一打 Details API 並寫入 DB ───────────────────────────
        stats = {'created': 0, 'skipped': 0, 'failed': 0}

        for i, place_id in enumerate(place_ids, start=1):
            self.stdout.write(f'[{i}/{len(place_ids)}] {place_id}')
            self._process_one(place_id, dry_run, stats)

            if i < len(place_ids):
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f'\n完成！\n'
                f'  新增: {stats["created"]} 筆\n'
                f'  略過（已存在）: {stats["skipped"]} 筆\n'
                f'  失敗: {stats["failed"]} 筆'
            )
        )

    # ------------------------------------------------------------------ #
    # place_id 來源
    # ------------------------------------------------------------------ #

    def _load_place_ids(self, options) -> list[str]:
        if options['url']:
            return self._fetch_place_ids_from_url(options['url'], options.get('save_ids'))

        if options['file']:
            return self._read_place_ids_from_file(options['file'])

        return options['ids']

    def _read_place_ids_from_file(self, path: str) -> list[str]:
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise CommandError(f'{path} 格式錯誤：必須是 JSON 陣列')
            return [str(item) for item in data]
        except FileNotFoundError:
            raise CommandError(f'找不到檔案：{path}')
        except json.JSONDecodeError as e:
            raise CommandError(f'JSON 格式錯誤：{e}')

    def _fetch_place_ids_from_url(self, url: str, save_path: str | None) -> list[str]:
        """
        用 Playwright 開啟 Google Maps 清單頁面，擷取所有 place_id。

        策略（依序嘗試）：
          1. 攔截 Maps API 回應（最可靠）：監聽 XHR，從 JSON 中 regex 出 ChIJ...
          2. 點擊每個清單項目，從跳轉後的 URL 解析 place_id
          3. 從完整頁面原始碼 regex（fallback）
        """
        self.stdout.write('啟動 Playwright 擷取清單...')

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise CommandError(
                'Playwright 未安裝，請先執行：\n'
                '  uv add playwright\n'
                '  uv run playwright install chromium'
            )

        place_ids: list[str] = []
        intercepted_ids: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.set_extra_http_headers({'Accept-Language': 'zh-TW,zh;q=0.9'})

            # ── 策略 1：監聽回應，不攔截（避免破壞重新導向） ──────────────
            def _on_response(response):
                try:
                    ct = response.headers.get('content-type', '')
                    if any(ct.startswith(t) for t in ('image/', 'font/', 'text/css', 'audio/', 'video/')):
                        return
                    body = response.text()
                    found = re.findall(r'ChIJ[A-Za-z0-9_\-]{10,45}', body)
                    for pid in found:
                        if pid not in intercepted_ids:
                            intercepted_ids.append(pid)
                except Exception:
                    pass

            page.on('response', _on_response)

            self.stdout.write(f'  開啟頁面：{url}')
            page.goto(url, wait_until='load', timeout=60000)
            page.wait_for_timeout(5000)

            self.stdout.write(f'  頁面標題：{page.title()}')
            self.stdout.write(f'  最終 URL ：{page.url}')

            # ── 捲動側邊欄，觸發懶載入 ────────────────────────────────────
            self._scroll_sidebar(page)

            # 攔截到的結果
            if intercepted_ids:
                self.stdout.write(f'  攔截到 {len(intercepted_ids)} 個 ChIJ id（網路回應）')
                place_ids = intercepted_ids

            # ── 策略 2：逐項點擊，從 URL 解析 ────────────────────────────
            if not place_ids:
                self.stdout.write('  嘗試逐項點擊...')
                place_ids = self._click_each_item(page)

            # ── 策略 3：頁面原始碼 regex ──────────────────────────────────
            if not place_ids:
                self.stdout.write(self.style.WARNING('  改用頁面原始碼 regex...'))
                content = page.content()
                place_ids = self._extract_ids_from_page_source(content)
                self.stdout.write(f'  regex 擷取到 {len(place_ids)} 個候選 place_id')

            # ── Debug：存側邊欄 HTML 供人工確認 ──────────────────────────
            self._dump_sidebar_html(page)

            # 存截圖
            page.screenshot(path='debug_maps.png')
            self.stdout.write('  截圖已存：debug_maps.png')

            browser.close()

        return self._finalize_ids(place_ids, save_path)

    def _scroll_sidebar(self, page):
        """捲動左側清單，觸發懶載入"""
        # 嘗試找到可捲動的側邊欄容器
        sidebar_selectors = [
            'div[role="feed"]',
            'div[aria-label*="結果"]',
            'div[aria-label*="清單"]',
            'div[aria-label*="Results"]',
            '.m6QErb',          # Google Maps 側欄常見 class（可能變動）
        ]
        container = None
        for sel in sidebar_selectors:
            el = page.query_selector(sel)
            if el:
                container = el
                self.stdout.write(f'  找到可捲動容器：{sel}')
                break

        for _ in range(15):
            if container:
                container.evaluate('el => el.scrollBy(0, 600)')
            else:
                page.keyboard.press('End')
            page.wait_for_timeout(800)

    def _dump_sidebar_html(self, page):
        """將側邊欄 HTML 存檔，供人工檢查 DOM 結構"""
        try:
            sidebar_selectors = ['div[role="feed"]', '.m6QErb', 'div[aria-label*="結果"]']
            for sel in sidebar_selectors:
                el = page.query_selector(sel)
                if el:
                    html = el.inner_html()
                    with open('debug_sidebar.html', 'w', encoding='utf-8') as f:
                        f.write(html)
                    self.stdout.write(f'  側邊欄 HTML 已存：debug_sidebar.html（{len(html)} bytes，selector={sel}）')
                    return
            # fallback：存整個 body
            html = page.inner_html('body')
            with open('debug_sidebar.html', 'w', encoding='utf-8') as f:
                f.write(html[:200_000])   # 最多存前 200 KB
            self.stdout.write('  已存 body HTML（前 200 KB）至 debug_sidebar.html')
        except Exception as e:
            self.stdout.write(f'  dump HTML 失敗：{e}')

    def _click_each_item(self, page) -> list[str]:
        """逐一點擊側邊欄項目，從 URL 或 data 屬性解析 place_id"""
        place_ids: list[str] = []

        # 先嘗試直接從 DOM 找所有含 /maps/place/ 的 href
        hrefs = page.evaluate('''() => {
            return Array.from(document.querySelectorAll("a[href]"))
                .map(a => a.getAttribute("href"))
                .filter(h => h && (h.includes("/maps/place/") || h.includes("place_id=")));
        }''')
        self.stdout.write(f'  JS 蒐集到 {len(hrefs)} 個 place href')
        for href in hrefs:
            pid = self._extract_place_id_from_href(href)
            if pid and pid not in place_ids:
                place_ids.append(pid)
        if place_ids:
            return place_ids

        # 嘗試找可點擊的地點卡片，逐一點擊後抓 URL
        card_selectors = [
            '.Nv2PK',                          # 地點卡片
            '[data-result-index]',              # 搜尋結果項目
            'div[role="article"]',              # aria article
            'div[jsaction*="placeCard"]',       # jsaction 含 placeCard
            '.hfpxzc',                          # 地點連結（有時是 div 非 a）
        ]
        cards = []
        for sel in card_selectors:
            cards = page.query_selector_all(sel)
            if cards:
                self.stdout.write(f'  找到 {len(cards)} 張卡片（{sel}）')
                break

        if not cards:
            self.stdout.write('  找不到任何卡片元素')
            return place_ids

        initial_url = page.url
        for i, card in enumerate(cards):
            try:
                card.click()
                page.wait_for_timeout(1500)
                current_url = page.url
                if current_url != initial_url:
                    pid = self._extract_place_id_from_href(current_url)
                    if pid and pid not in place_ids:
                        place_ids.append(pid)
                        self.stdout.write(f'    [{i+1}] 點擊後取得 {pid}')
                    # 嘗試返回列表
                    page.go_back(wait_until='load', timeout=5000)
                    page.wait_for_timeout(1000)
                    initial_url = page.url
            except Exception as e:
                self.stdout.write(f'    [{i+1}] 點擊失敗：{e}')

        return place_ids

    def _extract_place_id_from_href(self, href: str) -> str | None:
        """
        從 Google Maps 地點 URL 中解析 place_id。

        常見格式：
          /maps/place/店名/data=...!1s{place_id}!...
          /maps/place/店名/@lat,lng,...
        """
        # 格式一：URL 含有 place_id 參數
        m = re.search(r'place_id=([A-Za-z0-9_\-]+)', href)
        if m:
            return m.group(1)

        # 格式二：data 欄位內的 !1sChIJ...
        m = re.search(r'!1s(ChIJ[A-Za-z0-9_\-]+)', href)
        if m:
            return m.group(1)

        return None

    def _extract_ids_from_page_source(self, html: str) -> list[str]:
        """從頁面原始碼用正則擷取 ChIJ... 格式的 place_id（回退方案）"""
        found = re.findall(r'ChIJ[A-Za-z0-9_\-]{10,45}', html)
        # 去重，並過濾掉明顯太短或太長的
        seen = set()
        result = []
        for pid in found:
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    def _finalize_ids(self, place_ids: list[str], save_path: str | None) -> list[str]:
        """印出結果，選擇性另存 JSON"""
        self.stdout.write(self.style.SUCCESS(f'  擷取到 {len(place_ids)} 個 place_id'))

        if save_path:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(place_ids, f, ensure_ascii=False, indent=2)
            self.stdout.write(f'  已儲存至 {save_path}')

        return place_ids

    # ------------------------------------------------------------------ #
    # Details API + DB 寫入
    # ------------------------------------------------------------------ #

    def _process_one(self, place_id: str, dry_run: bool, stats: dict):
        if Cafe.objects.filter(place_id=place_id).exists():
            self.stdout.write('  → 略過（DB 已有此店）')
            stats['skipped'] += 1
            return

        detail = GoogleAPI.get_shop_detail(place_id)

        if not detail or not detail.get('place_id'):
            self.stdout.write(self.style.WARNING('  → 失敗：無法取得詳細資料'))
            stats['failed'] += 1
            return

        name = detail.get('name', '未知店名')
        self.stdout.write(f'  → {name}')

        if dry_run:
            self.stdout.write('     [dry-run] 會建立 Cafe + 2 筆 CafeAttributeVote')
            stats['created'] += 1
            return

        try:
            with transaction.atomic():
                cafe = self._create_cafe(detail)
                self._create_vote_records(cafe)
            self.stdout.write(self.style.SUCCESS('     ✓ 已建立'))
            stats['created'] += 1

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'     ✗ 寫入失敗：{e}'))
            logger.exception(f'seed_cafes_from_google 寫入失敗 place_id={place_id}')
            stats['failed'] += 1

    def _create_cafe(self, detail: dict) -> Cafe:
        opening_hours_d = parse_opening_hours(detail.get('opening_hours', []))

        return Cafe.objects.create(
            place_id=detail['place_id'],
            name=(detail.get('name') or '未提供名稱')[:200],
            address=(detail.get('address') or '未提供地址')[:300],
            phone=detail.get('phone') or '',
            rating=detail.get('rating'),
            user_ratings_total=detail.get('user_ratings_total', 0),
            google_maps=detail.get('google_maps') or '',
            website=detail.get('website') or '',
            lat=detail.get('lat') or 0.0,
            lng=detail.get('lng') or 0.0,
            opening_hours=opening_hours_d,
            photo_reference=detail.get('photo_reference') or '',  # 存 reference，照片本體延遲抓
            has_socket=SEED_SOCKET_VALUE,
            limited_time=SEED_LIMITED_TIME_VALUE,
            attributes_last_calculated_at=timezone.now(),
            last_refreshed=timezone.now(),
        )

    def _create_vote_records(self, cafe: Cafe):
        for attribute, value in [
            ('socket', SEED_SOCKET_VALUE),
            ('limited_time', SEED_LIMITED_TIME_VALUE),
        ]:
            CafeAttributeVote.objects.update_or_create(
                cafe=cafe,
                attribute=attribute,
                source='google',
                user=None,
                defaults={'value': value},
            )
