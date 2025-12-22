from django.db import models
from django.db.models import F

from users.models import User


# Create your models here.

class Cafe(models.Model):
    # 唯一key
    place_id = models.CharField(max_length=100, unique=True, db_index=True, verbose_name='Google Place ID')

    # 基本資料
    name = models.CharField(max_length=200, verbose_name='咖啡店名稱')
    address = models.TextField(max_length=300, verbose_name='地址')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='電話')

    # 地理位置
    lat = models.FloatField(blank=True, null=True, verbose_name='緯度')
    lng = models.FloatField(blank=True, null=True, verbose_name='經度')

    rating = models.DecimalField(max_digits=2, decimal_places=1, blank=True, null=True, verbose_name='Google 評分')
    user_ratings_total = models.IntegerField(default=0, verbose_name='評論數量')

    has_plug = models.BooleanField(null=True, blank=True, verbose_name='是否有插座')
    is_time_unlimited = models.BooleanField(null=True, blank=True, verbose_name='是否不限時')

    # 營業資訊
    opening_hours = models.JSONField(default=list, blank=True, verbose_name='營業時間')
    website = models.URLField(blank=True, null=True, verbose_name='官方網站')
    google_maps = models.URLField(blank=True, null=True, verbose_name='Google Maps 連結')

    favorite_count = models.IntegerField(default=0, verbose_name='收藏數')

    # 查詢資料是否有定期更新，每30天會更新資料（使用者若有查詢該筆資料）
    last_refreshed = models.DateTimeField(null=True, blank=True, verbose_name='資料最後更新時間')

    # photo
    photo_reference = models.CharField(blank=True, default='')
    photo_s3_url = models.URLField(blank=True)  # S3 URL（可為空）
    view_count = models.IntegerField(default=0)  # 追蹤熱門度

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def increment_favorite_count(self):
        """增加收藏數"""
        Cafe.objects.filter(
            pk=self.pk
        ).update(
            favorite_count=F('favorite_count') + 1
        )
        self.refresh_from_db(fields=['favorite_count'])
        # 避免 race condition

    def decrement_favorite_count(self):
        """減少收藏數"""
        if self.favorite_count > 0:
            Cafe.objects.filter(
                pk=self.pk, favorite_count__gt=0
            ).update(
                favorite_count=F('favorite_count') - 1
            )
            self.refresh_from_db(fields=['favorite_count'])
            # 避免 race condition

    def to_dict(self):
        """轉換成 Flex Message 需要的格式"""
        return {
            'name': self.name,
            'address': self.address,
            'phone': self.phone,
            'rating': self.rating,
            'user_ratings_total': self.user_ratings_total,
            'place_id': self.place_id,
            'google_maps': self.google_maps,
            'website': self.website,
            'lat': self.lat,
            'lng': self.lng,
            'opening_hours': self.opening_hours,
            'photo_reference': self.photo_reference,
        }

    @classmethod
    def get_popular_cafes(cls):
        return cls.objects.order_by('-favorite_count')[:10]

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'cafes'
        verbose_name = '咖啡店'
        verbose_name_plural = '咖啡店列表'
        indexes = [
            models.Index(fields=['-favorite_count']),
            models.Index(fields=['lat', 'lng']),  # 地理位置搜尋
        ]


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites', verbose_name='使用者')
    cafe = models.ForeignKey(Cafe, on_delete=models.CASCADE, related_name='favorited_by', verbose_name='咖啡店')

    note = models.TextField(blank=True, null=True, verbose_name='個人備註')
    is_public = models.BooleanField(default=False, verbose_name='公開收藏')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'favorites'
        verbose_name = '收藏'
        verbose_name_plural = '收藏列表'
        unique_together = ('user', 'cafe')
