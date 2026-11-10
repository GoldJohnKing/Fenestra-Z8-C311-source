# 竖拍自动旋转

**文件** `portrait_video.wlm`。冷启动后原生功能自动接入，`Z8Mouldes` 里的 `Portrait video rotation` 是插件入口。

配套 Nikon Z 8 C3.11 的 `cold-retry3`。复制到卡根目录的 `FENESTRA/` 后完整冷启动。[下载 portrait_video.wlm](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/download/wlm-2026.11.10/portrait_video.wlm) · [安装和停用](../z8-usage.zh-CN.md#安装插件)

## 拍摄与回放

拍摄前先把机身转到所需的竖拍方向，再按录制。插件在第一帧记录方向，支持旋转信息的播放器会把成片正立显示，编码分辨率保持原样。录制中转动机身仍沿用开录方向。可以分别录两段相反方向的竖拍和一段横拍，在电脑上确认显示方向。r3 已有 1080p MOV 两个方向、横拍和一段 N-RAW NEV 的实机文件检查，其他组合按实际录制设置验证。
