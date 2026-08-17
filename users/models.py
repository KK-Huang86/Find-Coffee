import logging
import random
import string

from django.core.exceptions import ValidationError
from django.db import models, IntegrityError, router, transaction

logger = logging.getLogger(__name__)


# Create your models here.


class User(models.Model):
    FREE = 1
    PREMIUM = 2

    MEMBER_TYPE_CHOICES = (
        (FREE, '一般會員'),
        (PREMIUM, '付費會員'),
    )

    ACTIVE = 1
    SUSPENDED = 2

    STATUS_CHOICES = (
        (ACTIVE, '啟用'),
        (SUSPENDED, '停用'),
    )

    line_user_id = models.CharField(max_length=50, unique=True, db_index=True, help_text='Line User ID')
    display_name = models.CharField(max_length=100, blank=True, null=True, verbose_name='使用者暱稱')
    member_code = models.CharField(max_length=10, unique=True, verbose_name='會員代號')
    member_type = models.PositiveSmallIntegerField(choices=MEMBER_TYPE_CHOICES, default=FREE, verbose_name='會員類型',
                                                   help_text='會員類型')
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, default=ACTIVE, verbose_name='帳號狀態',
                                              help_text='帳號是否啟用')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.line_user_id

    def save(self, *args, **kwargs):
        if self.member_code:
            super().save(*args, **kwargs)
            return

        using = kwargs.get('using') or router.db_for_write(self.__class__, instance=self)
        last_error = None
        for attempt in range(10):
            self.member_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            try:
                with transaction.atomic(using=using):
                    super().save(*args, **kwargs)
                return
            except IntegrityError as e:
                if 'member_code' not in str(e):
                    raise
                last_error = e  # 保存原始錯誤
                logger.warning(
                    f'member_code 撞號，觸發 rollback 並重試 (attempt {attempt + 1}/10)，'
                    f'line_user_id={self.line_user_id}'
                )

        # 執行 10 次都失敗
        logger.error(
            f'member_code 重試 10 次仍撞號，建立失敗，line_user_id={self.line_user_id}'
        )
        raise IntegrityError(
            f'Failed to generate a unique member_code after {attempt + 1} attempts.'
        ) from last_error

    class Meta:
        db_table = 'users'
        verbose_name = '使用者'
        verbose_name_plural = '使用者列表'


class Friendship(models.Model):
    """好友關係"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friendships')
    friend = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friend_of')

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.user == self.friend:
            raise ValidationError('使用者不能加自己為好友')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'friendships'
        unique_together = [['user', 'friend']]

        constraints = [
            models.CheckConstraint(
                condition=~models.Q(user=models.F('friend')),  # 驗證user是否!=friend
                name='prevent_self_friendship'
            )
        ]
