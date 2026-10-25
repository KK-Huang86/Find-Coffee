import pytest


@pytest.fixture(autouse=True)
def block_google_shop_detail(mocker):
    """過期店家會在請求流程中同步刷新；預設擋下 Places Detail 真實呼叫（回傳空資料，視同刷新失敗），
    需要特定回應的測試再自行 patch"""
    return mocker.patch('cafe.tasks.GoogleAPI.get_shop_detail', return_value={})
