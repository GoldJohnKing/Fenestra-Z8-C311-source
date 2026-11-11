# 竖拍自动旋转

**文件** `portrait_video.wlm`。冷启动后原生功能自动接入，`Z8Mouldes` 里的 `Portrait video rotation` 是插件入口。

配套 Nikon Z 8 C3.11 的 `cold-retry3`。复制到卡根目录的 `FENESTRA/` 后完整冷启动。[下载 portrait_video.wlm](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/download/wlm-2026.11.10-r10/portrait_video.wlm) · [安装和停用](../z8-usage.zh-CN.md#安装插件)

## 拍摄与回放

拍摄前先把机身转到所需方向，再按录制。竖拍两个方向和 180° 倒置的成片带有旋转信息，支持旋转信息的播放器会把它们正立显示。镜头朝上或朝下拍摄的成片不带旋转信息。编码分辨率保持原样。

成片方向按采样时刻的持机方向记录。H.265 10-bit、ProRes 422 HQ、ProRes RAW 和 N-RAW 在开录时采样。录制中转动机身，这类档位的成片仍按开录方向显示。H.264 档位与 H.265 8-bit 档位（不可切换色调模式的格式）在停录时采样。停录后立刻大幅转动机身，这类档位的成片方向可能标错。

## 已知限制

机内导出或转码得到的文件带有导出时刻的方向，不带有素材拍摄时的方向。需要精确方向的素材请在电脑上处理。
