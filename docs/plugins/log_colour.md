# Log 色彩

**文件** `log_colour.wlm`，**入口** 设定菜单 → Z8Mouldes → Log 色彩 → Log / 色域。

配套 Nikon Z 8 C3.11 的 `cold-retry3`。复制到卡根目录的 `FENESTRA/` 后完整冷启动。[下载 log_colour.wlm](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/download/wlm-2026.11.10-r10/log_colour.wlm) · [安装和停用](../z8-usage.zh-CN.md#安装插件)

## 机内设置与后期

1. 在视频拍摄菜单选择支持 Log 的录像类型，例如 H.265 10 位或 ProRes 422，再把色调设为 Log。
2. 在插件页选 N-Log、S-Log3 或 Log3G10，按需开启机内显示辅助。显示辅助只用于监看。
3. 剪辑时按拍摄选择指定输入曲线和色域，尤其是在剪辑软件自动识别结果与拍摄设置不一致时。

| 拍摄选择 | 剪辑软件的输入曲线 | 剪辑软件的输入色域 |
| --- | --- | --- |
| N-Log | Nikon N-Log | BT.2020 / Rec.2020 |
| S-Log3 | Sony S-Log3 | Sony S-Gamut3.Cine |
| Log3G10 | RED Log3G10 | REDWideGamutRGB |

这张表用于已编码的 H.265 和 ProRes 422 Log 片段。N-RAW 和 ProRes RAW 的输入由剪辑软件的 RAW 解码设置决定。

## 功能来源与移植

本插件使用 NikonFirmwarePatch v0.4.0-rc.2 的对应功能实现，并适配为 Fenestra WLM。[对应源码](https://github.com/XinmiaoZhao/NikonFirmwarePatch/tree/a21fc8c04b6dd863439c4192d387b755633287f6)
