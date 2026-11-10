# 照片工具

**文件** `photo_tools.wlm`（r10），**入口** 设定菜单 → Z8Mouldes → 照片工具。RAW 预拍由相机原厂拍摄入口操作，插件页显示提示和当前 RAW 格式。

配套 Nikon Z 8 C3.11 的 `cold-retry3`。复制到卡根目录的 `FENESTRA/` 后完整冷启动。[下载 photo_tools.wlm](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/download/wlm-2026.11.10-r10/photo_tools.wlm) · [安装和停用](../z8-usage.zh-CN.md#安装插件)

## C15/C30 RAW 连拍和预拍

1. 在照片模式选择 **FX 或 DX、L 尺寸、C15 或 C30**。
2. 在相机「图像品质」选 RAW 或 RAW+JPEG，在「RAW 记录」选 HE 或 HE★。在此高速路径里，选择「无损压缩」也会写出 HE★。这一组设置适用于 C15 和 C30。
3. 在自定义设定 `d3` 的预拍摄选项设预拍时长。半按快门缓存画面，全按保存预拍和正式帧。拍完等写卡结束，再检查生成的 NEF 和所选 JPEG。[半按和全按的原厂操作](https://onlinemanual.nikonimglib.com/z8/en/csmd_pre-release_capture_options_233.html)

## 在 r10 开启 C40、C140

下载本页链接的 **r10** 文件，替换卡上的旧 `photo_tools.wlm`。完整冷启动后，打开 **设定菜单 → Fenestra → Activate**，再进入并列的 **Z8Mouldes → 照片工具**。

| 要拍的速度 | 相机的释放模式 | 在「照片工具」里选 |
| --- | --- | --- |
| C40 | **C30** | 「C30 连拍速度」→「40 张/秒（FX 仅RAW）」 |
| C140 | **C120** | 「C120 连拍速度」→「140 张/秒（仅RAW）」 |

1. 用**照片模式、FX 画幅**。在相机「图像品质」选 **RAW（仅 RAW）**，「RAW 记录」可先选 **HE**。C120/C140 的 RAW 路径使用单卡，双卡时把副卡槽功能设为「额外空间」。
2. 选表中的释放模式和插件档位，然后回到取景界面拍摄。相机释放模式仍按 C30 或 C120 进入，实际速度由插件里的选项控制。[尼康释放模式入口](https://onlinemanual.nikonimglib.com/z8/en/release_mode_33.html)
3. 首次可先关掉预拍，用一小段连拍检查生成的 NEF，再按需要调 `d3` 的预拍和后拍。拍摄结束等写卡灯熄灭。要恢复原速，在同一行选 30 或 120 张/秒。完整冷启动后，这些速度开关从默认档开始。

### DX C60 与 FX C120

- **DX C60 RAW** 使用照片模式、DX、相机的 C60 档、RAW（仅 RAW）。以 60 张/秒拍摄。用单卡或将副卡设为「额外空间」。r10 可通过 `d3` 设置预拍。
- **FX C120 RAW** 使用照片模式、FX、C120、RAW（仅 RAW）。在「C120 连拍速度」选 120 张/秒，卡槽条件与 C140 相同。
- DX C60、FX C120 和 C140 的 RAW 路径输出 HE。

r10 关闭了 r10p 的 NVMe/FileService 分段写卡计时，保留基础计数和整轮摘要。高速连拍属于实验功能，持续写入和实际帧率以拍摄文件为准。

### RAW 解码兼容性

以下是这两个高速 RAW 档位已知的解码情况。

| 拍摄档位 | 已知无法解码 | 已知可解码 |
| --- | --- | --- |
| DX C60 RAW | Capture One | 像素蛋糕 |
| FX C120 RAW | Adobe Camera Raw（ACR）、Capture One | 像素蛋糕 |

## 像素位移合并

1. 用相机的像素位移拍摄取得一组完整的 **4、8、16 或 32 张 FX/L、14 位无损压缩 NEF**，等写卡结束。HE/HE★、DX、缺帧的组和上面 RAW 预拍生成的帧不适用。
2. 在「照片工具」里用「合并组」选择「最新未合并组」或「所有未合并组」，把「确认合并」改为「是」，再按「开始合并」。要手动选具体的组，可以用原厂照片拍摄菜单里的「像素变化合成」。
3. 在「合并状态」看进度。需要中止时按「取消合并」，等写入关闭后再关机或取卡。输出是在原照片目录里新增的 `_MERGED.NEFX` 文件，可拷到电脑查看。4/8 张组输出 8256×5504，16/32 张组输出 16512×11008，原片会保留。

## 功能来源与移植

本插件使用 NikonFirmwarePatch v0.4.0-rc.2 的对应功能实现，并适配为 Fenestra WLM。r10 在此基础上增加高速 RAW 档位。[对应源码](https://github.com/XinmiaoZhao/NikonFirmwarePatch/tree/a21fc8c04b6dd863439c4192d387b755633287f6)

[从源码构建 r10](../z8-build.zh-CN.md#照片工具-r10)
