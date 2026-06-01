import time
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from line_bot.views import configuration  # noqa: E402
from linebot.v3.messaging import ApiClient, MessagingApi  # noqa: E402

with ApiClient(configuration) as api_client:
    api = MessagingApi(api_client)
    menus = api.get_rich_menu_list().richmenus or []
    total = len(menus)
    print(f"共 {total} 個，開始刪除...")

    for i, menu in enumerate(menus):
        success = False
        for attempt in range(10):
            try:
                api.delete_rich_menu(rich_menu_id=menu.rich_menu_id)
                print(f"[{i+1}/{total}] 刪除成功")
                time.sleep(1)
                success = True
                break
            except Exception as e:
                if '429' in str(e):
                    print(f"[{i+1}/{total}] Rate limited，等 30 秒...")
                    time.sleep(30)
                else:
                    raise
        if not success:
            print(f"[{i+1}/{total}] 跳過")

print("完成！")
