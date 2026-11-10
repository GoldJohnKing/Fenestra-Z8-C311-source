# 画幅与 N-RAW

**文件** `framing.wlm`，**入口** 设定菜单 → Z8Mouldes → 画幅 / N-RAW。

配套 Nikon Z 8 C3.11 的 `cold-retry3`。复制到卡根目录的 `FENESTRA/` 后完整冷启动。[下载 framing.wlm](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/download/wlm-2026.11.10/framing.wlm) · [安装和停用](../z8-usage.zh-CN.md#安装插件)

## 录像和构图

- **3:2 开放画幅**。先在视频文件类型选择 N-RAW，再到视频拍摄菜单的「画面尺寸 / 帧频」选择 8.3K 的 `[FX 3:2]` 30p、25p 或 24p。插件页显示开放画幅的选择状态。要回到常用宽屏比例，改回原厂 16:9 项。
- **N-RAW 品质**。在插件页选「高」「精细」「标准」或「基本」。不同档位的压缩程度不同。
- **变形镜头还原**。在插件页按镜头标注选倍率，例如 1.33× 或 2.00×。后屏、取景器和回放按该倍率显示，录像保留原始像素比例，后期按同一倍率还原。用普通镜头时选择「关闭」。

## 功能来源与移植

本插件使用 NikonFirmwarePatch v0.4.0-rc.2 的对应功能实现，并适配为 Fenestra WLM。[对应源码](https://github.com/XinmiaoZhao/NikonFirmwarePatch/tree/a21fc8c04b6dd863439c4192d387b755633287f6)
