"""
補產缺漏的咖啡店 AI 摘要（ai_summary）

找出 ai_summary 為空值或純空白、且有 Google 評論的店家，逐筆排入 generate_cafe_ai_summary 背景任務。
額度在任務內扣除（系統帳號，與真人使用者分開），這裡只依剩餘額度預估本次排入數量。

使用方式：
    # 試跑：只列出會處理的店家數量，不排入任務
    uv run python manage.py backfill_ai_summary --dry-run

    # 最多處理 20 間（每筆間隔預設 25 秒）
    uv run python manage.py backfill_ai_summary --limit 20
"""

import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from cafe.models import Cafe
from cafe.tasks import generate_cafe_ai_summary
from integrations.services import ApiUsageService
from utils.utils import LockService

logger = logging.getLogger(__name__)

LOCK_ACTION = 'ai_summary_backfill'
# 已排入的店家在此期間內不會被重複排入（任務通常數秒內完成，留足 broker 排隊時間）
LOCK_TTL_SECONDS = 600
# Groq gpt-oss-20b TPM 上限 8000、每次摘要約 2–3k tokens（含推理），每分鐘最多約 3 筆
DEFAULT_INTERVAL_SECONDS = 25.0


def _non_negative_int(value):
    number = int(value)
    if number < 0:
        raise ValueError(value)
    return number


def _non_negative_float(value):
    number = float(value)
    if number < 0:
        raise ValueError(value)
    return number


class Command(BaseCommand):
    help = '補產缺漏的咖啡店 AI 摘要（只處理沒有摘要且有評論的店家）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='模擬執行：只列出會處理的店家數量，不排入任務',
        )
        parser.add_argument(
            '--limit',
            type=_non_negative_int,
            default=None,
            help='本次最多排入幾間（預設不限，但仍受系統 AI 剩餘額度限制）',
        )
        parser.add_argument(
            '--interval',
            type=_non_negative_float,
            default=DEFAULT_INTERVAL_SECONDS,
            help=f'每筆排入之間的間隔秒數，避免超過 Groq TPM 上限（預設 {DEFAULT_INTERVAL_SECONDS:g} 秒）',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        interval = options['interval']

        targets = (
            # TRIM 只去除空格不含換行，純空白判斷改用 regex
            Cafe.objects.filter(Q(ai_summary__isnull=True) | Q(ai_summary__regex=r'^\s*$'))
            .exclude(reviews__isnull=True)
            .exclude(reviews=[])
            .order_by('id')
        )
        total = targets.count()
        self.stdout.write(f'缺少 AI 摘要且有評論的店家：{total} 間')

        if dry_run:
            for cafe in targets[:limit] if limit is not None else targets:
                self.stdout.write(f'  - {cafe.id} {cafe.name} ({cafe.place_id})')
            self.stdout.write('試跑模式，未排入任何任務')
            return

        system_user_id = ApiUsageService.get_system_ai_user_id()
        remaining = ApiUsageService.get_remaining_ai_calls(system_user_id)
        if remaining == 0:
            self.stdout.write(self.style.WARNING('系統 AI 額度已用盡，本月無法補產'))
            return

        max_queue = remaining if limit is None else min(limit, remaining)
        if total > remaining and (limit is None or limit > remaining):
            self.stdout.write(self.style.WARNING(
                f'系統 AI 剩餘額度只有 {remaining} 次，本次最多排入 {remaining} 間，其餘請下個月再執行'
            ))

        queued = 0
        skipped = 0
        for cafe in targets.iterator(chunk_size=200):
            if queued >= max_queue:
                break
            if not LockService.acquire(str(cafe.id), LOCK_ACTION, ttl=LOCK_TTL_SECONDS):
                skipped += 1
                continue

            if queued > 0 and interval:
                time.sleep(interval)

            try:
                generate_cafe_ai_summary.delay(cafe.id)
            except Exception as e:
                LockService.release(str(cafe.id), LOCK_ACTION)
                logger.error(f'排入 AI 摘要任務失敗，中止補產: cafe_id={cafe.id}, error={e}', exc_info=True)
                raise CommandError(f'排入 cafe_id={cafe.id} 失敗（{e}），已成功排入 {queued} 間') from e

            queued += 1
            logger.info(f'已排入 AI 摘要補產任務: cafe_id={cafe.id}')

        self.stdout.write(self.style.SUCCESS(
            f'已排入 {queued} 間；略過 {skipped} 間（{LOCK_TTL_SECONDS // 60} 分鐘內已排入過）'
        ))
