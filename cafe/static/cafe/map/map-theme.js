// 在頁面渲染前套用主題，避免深色模式閃白；CSP 不允許 inline script，所以獨立成檔案同步載入
(function () {
  var stored = null;
  try {
    stored = window.localStorage.getItem('find-coffee-map:theme');
  } catch (e) {
    // 瀏覽器封鎖本機儲存時改用系統偏好
  }
  var theme = stored === 'light' || stored === 'dark'
    ? stored
    : (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', theme);
})();
