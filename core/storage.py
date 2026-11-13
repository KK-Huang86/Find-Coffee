from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticStorage(CompressedManifestStaticFilesStorage):
    """WhiteNoise manifest storage，並改寫 ES module 的 import 路徑為 hash 後檔名

    咖啡地圖的 map-app.js 以 `import ... from './map-core.js'` 載入相依模組；
    不改寫時 hash 後的 map-app 會載入未 hash、只快取 60 秒的 map-core，部署後可能新舊版本混用
    """
    support_js_module_import_aggregation = True
