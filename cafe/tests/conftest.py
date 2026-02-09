import pytest
from django.conf import settings


@pytest.fixture(scope='session')
def django_db_setup():
    """使用 SQLite 跑測試"""
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }


@pytest.fixture
def mock_google_api(mocker):
    """Mock GoogleAPI.get_shop_detail"""
    return mocker.patch('cafe.tasks.GoogleAPI.get_shop_detail')


@pytest.fixture
def mock_photo_task(mocker):
    """Mock download_and_upload_cafe_photo.delay"""
    return mocker.patch('cafe.tasks.download_and_upload_cafe_photo.delay')
