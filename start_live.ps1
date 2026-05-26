# 闲鱼 AI 自动回复启动脚本
# 清除代理环境变量（避免 websockets 走代理报错）
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""

Write-Host "=== 闲鱼 AI 自动回复启动 ===" -ForegroundColor Green
Write-Host "请用闲鱼 App 扫描终端中的二维码登录" -ForegroundColor Yellow

cd C:\Users\Administrator\XianYuApis
python goofish_live.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n脚本异常退出，错误码: $LASTEXITCODE" -ForegroundColor Red
    pause
}
