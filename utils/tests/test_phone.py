import pytest

from utils.phone import build_tel_uri


class TestBuildTelUri:
    """測試 utils.phone.build_tel_uri"""

    @pytest.mark.parametrize('phone, expected', [
        ('02 2345 6789', 'tel:0223456789'),
        ('02-2345-6789', 'tel:0223456789'),
        ('(02) 2345-6789', 'tel:0223456789'),
        ('0912 345 678', 'tel:0912345678'),
        ('+886 2 2345 6789', 'tel:+886223456789'),
        ('  02 2345 6789  ', 'tel:0223456789'),
    ])
    def test_strips_separators(self, phone, expected):
        """移除空白、連字號、括號，保留開頭 +"""
        assert build_tel_uri(phone) == expected

    @pytest.mark.parametrize('phone', [
        '02-2345-6789 #123',
        '02-2345-6789#123',
        '02-2345-6789 分機 123',
        '02-2345-6789 ext. 123',
        '02-2345-6789 EXT 123',
        '02-2345-6789 轉 123',
        '02-2345-6789, 123',
        '02-2345-6789;123',
    ])
    def test_truncates_extension(self, phone):
        """分機標記之後的內容不併入號碼"""
        assert build_tel_uri(phone) == 'tel:0223456789'

    def test_full_width_digits(self):
        """全形數字與符號轉半形"""
        assert build_tel_uri('０２－２３４５－６７８９') == 'tel:0223456789'

    def test_plus_only_kept_at_start(self):
        """非開頭的 + 視為分隔符號移除"""
        assert build_tel_uri('02+2345+6789') == 'tel:0223456789'

    @pytest.mark.parametrize('phone', ['無提供', '未提供電話', '電話未提供', '', '   ', '---', '+'])
    def test_placeholder_or_no_digits_returns_none(self, phone):
        """佔位字串或不含數字時回傳 None"""
        assert build_tel_uri(phone) is None

    @pytest.mark.parametrize('phone', [None, 223456789, 2.5, ['02 2345 6789'], {'phone': '02'}])
    def test_non_string_returns_none(self, phone):
        """非字串輸入回傳 None"""
        assert build_tel_uri(phone) is None

    def test_min_length_boundary(self):
        """3 位數字為下限（含），2 位不合法"""
        assert build_tel_uri('110') == 'tel:110'
        assert build_tel_uri('11') is None

    def test_max_length_boundary(self):
        """15 位數字為上限（含），16 位不合法"""
        assert build_tel_uri('1' * 15) == f'tel:{"1" * 15}'
        assert build_tel_uri('1' * 16) is None
        assert build_tel_uri('+' + '1' * 16) is None

    def test_extension_only_returns_none(self):
        """只有分機標記、前面無號碼時回傳 None"""
        assert build_tel_uri('#123') is None
