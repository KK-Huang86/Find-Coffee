from django.db import models
from users.models import User

# Create your models here.


class ApiUsageRecord(models.Model):
    """API 使用次數記錄"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='api_usage_records', verbose_name='使用者'
    )

    # 記錄月份（例如：2025-01）
    year_month = models.CharField(max_length=7, verbose_name='年月', db_index=True)

    # 使用次數統計
    total_api_calls = models.IntegerField(default=0, verbose_name='總 API 呼叫次數')
    search_calls = models.IntegerField(default=0, verbose_name='搜尋 API 次數')
    detail_calls = models.IntegerField(default=0, verbose_name='詳細資訊 API 次數')

    # 是否可繼續使用
    can_use = models.BooleanField(default=True, verbose_name='是否可使用')

    # 額度限制（從 config 取得，但儲存在這裡方便查詢）
    monthly_limit = models.IntegerField(default=100, verbose_name='當月額度')

    # AI (Groq) 使用次數統計
    ai_calls = models.IntegerField(default=0, verbose_name='AI API 次數')
    can_use_ai = models.BooleanField(default=True, verbose_name='是否可使用 AI')
    monthly_ai_limit = models.IntegerField(default=50, verbose_name='當月 AI 額度')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'api_usage_records'

        unique_together = [['user', 'year_month']]

        ordering = ['-year_month']

        verbose_name = 'API 使用記錄'

        verbose_name_plural = 'API 使用記錄列表'

    def __str__(self):
        return f'{self.user.display_name or self.user.line_user_id[:8]} - {self.year_month} ({self.total_api_calls}/{self.monthly_limit})'
