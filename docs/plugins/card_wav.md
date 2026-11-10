# 卡内 WAV 快门声

**文件** `card_wav.wlm`，**选曲入口** 扳手设定菜单 → 照相机声音 → 快门音类型 → `Load WAV from card`。

配套 Nikon Z 8 C3.11 的 `cold-retry3`。复制到卡根目录的 `FENESTRA/` 后完整冷启动。[下载 card_wav.wlm](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/download/wlm-2026.11.10/card_wav.wlm) · [安装和停用](../z8-usage.zh-CN.md#安装插件)

## 放入音频并选曲

在卡根目录创建 `CUSTOM_SOUND/`，放入 **48 kHz、16 位 PCM、立体声 WAV**，最长 **1.5 秒**，单个 WAV 容器最多 512 KiB。文件名用可打印 ASCII 字符，含 `.wav` 最多 111 字符，列表最多显示 20 个文件。冷启动后按上述路径选曲，外层快门音类型显示 `CUS`。同名 WAV 换过内容时重新选一次。

要暂时改回原厂快门声，可在机内选 A–E。需要停用整个 WLM 时，在 Fenestra 的 Modules 里关闭，再完整冷启动。

## 功能来源与移植

本插件由 z8-card-wav v0.1.1 适配为 Fenestra WLM，快门声实现源自 s3lemming 的 Z9 卡内 WAV 方案。[z8-card-wav](https://github.com/PIPA12344/z8-card-wav/releases/tag/v0.1.1) · [Z9 实现](https://github.com/s3lemming/z9-firmware-patch/tree/88a6f3e5195d7f38792dc8eddeb1526fde4096dc)
