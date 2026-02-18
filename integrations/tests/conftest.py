import pytest
from django.conf import settings


@pytest.fixture(scope='session')
def django_db_setup():
    """使用 SQLite 跑測試"""
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
