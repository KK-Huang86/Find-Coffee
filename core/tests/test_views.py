import pytest
from django.test import Client


@pytest.mark.django_db
class TestLiveness:
    def test_returns_200(self):
        client = Client()
        response = client.get('/health/live/')
        assert response.status_code == 200
        assert response.json() == {'status': 'ok'}


@pytest.mark.django_db
class TestReadiness:
    def test_returns_200_when_db_available(self):
        client = Client()
        response = client.get('/health/ready/')
        assert response.status_code == 200
        assert response.json() == {'status': 'ok'}

    def test_returns_503_when_db_unavailable(self, mocker):
        mocker.patch(
            'django.db.connection.cursor',
            side_effect=Exception('db connection failed'),
        )
        client = Client()
        response = client.get('/health/ready/')
        assert response.status_code == 503
        assert response.json()['status'] == 'error'
