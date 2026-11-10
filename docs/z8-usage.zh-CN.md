# Fenestra Z8 C3.11 使用手册

这份手册对应 `wlm-2026.11.10` 的七个 WLM。相机需为 Nikon Z 8，配套底座为 **`cold-retry3`**。固件在本地构建，插件可以直接下载。Fenestra 仍处于实验阶段，WonderLantern/Fenestra 已提示潜在变砖风险。[WLM 下载](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/tag/wlm-2026.11.10) · [Fenestra 项目说明](https://github.com/WonderLantern/Fenestra)

## 准备底座

相机已经运行 `cold-retry3` 时，直接跳到[安装插件](#安装插件)。工作台返回的 `build_identity` 可用来确认底座，预期值为 `f06231d84970cda74ff6afcdb2aad7d03f6fe0bc4a3ec76c15a9cfd40654579a`。

自行构建需要 Windows x64、Python 3.11+ 和 Windows x64 LLVM **19.1.5**。构建脚本固定接受 99,051,117 字节的官方 `Z_8_0311.bin`，输入 SHA-256 为 `d67413c2ede6b9ce8887175f20700bd9fbad2a973a4820968c45503d15d80d96`。[尼康原始文件](https://download.nikonimglib.com/archive8/wP5Vr003qbpC07ibhJ666rmRfF47/Z_8_0311.bin) · [尼康备用下载](https://download.nikonimglib.com/archive8/ulkCY0035nUW07Elwhy66zV8P546/Z_8_0311.bin) · [LLVM 19.1.5](https://github.com/llvm/llvm-project/releases/tag/llvmorg-19.1.5)

在 PowerShell 中准备本地环境。

```powershell
git clone --branch cold-retry3-source --single-branch https://github.com/PIPA12344/Fenestra-Z8-C311-source.git Fenestra-cold-retry3
cd Fenestra-cold-retry3
py -3 -m venv .venv
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r requirements-z8.txt
New-Item -ItemType Directory -Path inputs -Force
```

将下载的文件放到 `inputs/Z_8_0311.bin`。把 `$llvm` 改成 LLVM 19.1.5 的实际 `bin` 路径，运行以下命令。

```powershell
$llvm = 'C:\Program Files\LLVM\bin'
& $py -B scripts/build_cold_retry3.py --firmware inputs/Z_8_0311.bin --llvm-bin $llvm
Get-FileHash -Algorithm SHA256 -LiteralPath build/cold-retry3/Z_8_0311.bin
```

脚本会检查原始文件、编译并校验核心，再封装成本地底座 `build/cold-retry3/Z_8_0311.bin`。成品 SHA-256 应为 `0a9cdd079ab09136982a7bbcb2f3c0ffbe64a12f79cff27d5d5a5da833d7ee43`。构建在电脑上完成。选择在机身上使用实验底座时，通过「设定菜单 → 固件版本」的更新入口使用这个本地成品，按机内提示操作；机身已经运行 `cold-retry3` 时可以直接装插件。重新构建可用 `--output-dir build/cold-retry3-check` 指定新目录。[固定源码](https://github.com/PIPA12344/Fenestra-Z8-C311-source/tree/cold-retry3-source)

## 安装插件

1. 从 Release 下载需要的 `.wlm`，用 `SHA256SUMS.txt` 核对文件。七个插件可以任选，多个一起装时使用同一 Release 的文件。[WLM 下载](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/tag/wlm-2026.11.10)
2. 正常关机并等卡访问灯熄灭，再把 WLM 按原名复制到启动卡根目录的 `FENESTRA/`。两个卡槽都有这个目录时，底座优先选 CFexpress/XQD 卡槽 A。只用 SD 时，在卡槽 B 的卡上建目录。
3. 换好卡后做一次完整冷启动。关机、等访问灯熄灭、断开 USB，再取下电池片刻，装回后开机。普通的快速关开可能恢复原来的内存状态，冷启动才会重新读取卡上的插件。
4. 在扳手设定菜单打开 **Fenestra**。`Status` 显示 `Ready` 时可按 `Activate`，变成 `Active` 后，从设定菜单并列的 **Z8Mouldes** 打开插件页。希望启动后自动激活时，在 Fenestra 里把 `Auto activate` 设为 `On`。

目录示例，卡内 WAV 音频和 WLM 分开存放。

```text
存储卡根目录/
├─ FENESTRA/
│  ├─ framing.wlm
│  └─ card_wav.wlm
└─ CUSTOM_SOUND/
   └─ shutter.wav
```

`Auto activate` 关闭时，`Ready` 表示插件页面还等着手动激活。底座已经在冷启动时装入启用的原生组件，所以部分尼康原厂菜单项在 `Ready` 时就可能出现。

### 更新、停用和移除

- 更新时用同名新文件替换旧文件，再完整冷启动。备份放在 `FENESTRA/` 外。每个 ID 只保留一个版本，`prores.wlm` 和 `prores.wlm.disabled` 也只留其一。
- 在 **Fenestra → Modules** 关闭插件，或在关机后用读卡器把扩展名改为 `.wlm.disabled`。要移除则把该文件移出目录。冷启动后按卡上的新状态装载。
- 录像、合并和写卡结束后再关机、换卡或修改插件。切换视频档位也应在停止录制后进行。

## 七个插件怎么用

### 画幅与 N-RAW

**文件** `framing.wlm`，**入口** 设定菜单 → Z8Mouldes → 画幅 / N-RAW。

- **3:2 开放画幅**。先在视频文件类型选择 N-RAW，再到视频拍摄菜单的「画面尺寸 / 帧频」选择 8.3K 的 `[FX 3:2]` 30p、25p 或 24p。插件页显示开放画幅的选择状态。要回到常用宽屏比例，改回原厂 16:9 项。
- **N-RAW 品质**。在插件页选「高」「精细」「标准」或「基本」。不同档位的压缩程度不同。
- **变形镜头还原**。在插件页按镜头标注选倍率，例如 1.33× 或 2.00×。后屏、取景器和回放按该倍率显示，录像保留原始像素比例，后期按同一倍率还原。用普通镜头时选择「关闭」。

### ProRes 品质

**文件** `prores.wlm`，**入口** 设定菜单 → Z8Mouldes → ProRes 品质 → 品质。

先把视频文件类型设为 **ProRes 422**，部分菜单中入口仍显示 **ProRes 422 HQ**。停止录制后在插件页选 HQ（默认）、标准（422）、LT 或 Proxy。档位影响 ProRes 422 的压缩和文件大小，沿用原有画幅和帧率。需要核对录制结果时，四档 MOV 编码标识依次为 `apch`、`apcn`、`apcs`、`apco`。

### H.265 码率

**文件** `h265.wlm`，**入口** 设定菜单 → Z8Mouldes → H.265 码率 → 码率。

先选 H.265 文件类型和所需的画面尺寸、帧率，再选 100%（默认）、60%、45%、30% 或 20%。百分比以该模式的原厂标称码率为基准，100% 对应原厂档。菜单中的 Mbps 是目标值，实际录像大小会随场景变化。切换视频拍摄菜单库后可在对应库单独设置。

### Log 色彩

**文件** `log_colour.wlm`，**入口** 设定菜单 → Z8Mouldes → Log 色彩 → Log / 色域。

1. 在视频拍摄菜单选择支持 Log 的录像类型，例如 H.265 10 位或 ProRes 422，再把色调设为 Log。
2. 在插件页选 N-Log、S-Log3 或 Log3G10，按需开启机内显示辅助。显示辅助只用于监看。
3. 剪辑时按拍摄选择指定输入曲线和色域，尤其是在剪辑软件自动识别结果与拍摄设置不一致时。

| 拍摄选择 | 剪辑软件的输入曲线 | 剪辑软件的输入色域 |
| --- | --- | --- |
| N-Log | Nikon N-Log | BT.2020 / Rec.2020 |
| S-Log3 | Sony S-Log3 | Sony S-Gamut3.Cine |
| Log3G10 | RED Log3G10 | REDWideGamutRGB |

这张表用于已编码的 H.265 和 ProRes 422 Log 片段。N-RAW 和 ProRes RAW 的输入由剪辑软件的 RAW 解码设置决定。

### 照片工具

**文件** `photo_tools.wlm`，**入口** 设定菜单 → Z8Mouldes → 照片工具。RAW 预拍由相机原厂拍摄入口操作，插件页显示提示和当前 RAW 格式。

**RAW 连拍和预拍**

1. 在照片模式选择 **FX 或 DX、L 尺寸、C15 或 C30**。
2. 在相机「图像品质」选 RAW 或 RAW+JPEG，在「RAW 记录」选 HE 或 HE★。在此高速路径里，选择「无损压缩」也会写出 HE★。本发布的 RAW 路径范围为 C15 和 C30。
3. 在自定义设定 `d3` 的预拍摄选项设预拍时长。半按快门缓存画面，全按保存预拍和正式帧。拍完等写卡结束，再检查生成的 NEF 和所选 JPEG。[半按和全按的原厂操作](https://onlinemanual.nikonimglib.com/z8/en/csmd_pre-release_capture_options_233.html)

**像素位移合并**

1. 用相机的像素位移拍摄取得一组完整的 **4、8、16 或 32 张 FX/L、14 位无损压缩 NEF**，等写卡结束。HE/HE★、DX、缺帧的组和上面 RAW 预拍生成的帧不适用。
2. 在「照片工具」里用「合并组」选择「最新未合并组」或「所有未合并组」，把「确认合并」改为「是」，再按「开始合并」。要手动选具体的组，可以用原厂照片拍摄菜单里的「像素变化合成」。
3. 在「合并状态」看进度。需要中止时按「取消合并」，等写入关闭后再关机或取卡。输出是在原照片目录里新增的 `_MERGED.NEFX` 文件，可拷到电脑查看。4/8 张组输出 8256×5504，16/32 张组输出 16512×11008，原片会保留。

### 卡内 WAV 快门声

**文件** `card_wav.wlm`，**选曲入口** 扳手设定菜单 → 照相机声音 → 快门音类型 → `Load WAV from card`。

在卡根目录创建 `CUSTOM_SOUND/`，放入 **48 kHz、16 位 PCM、立体声 WAV**，最长 **1.5 秒**，单个 WAV 容器最多 512 KiB。文件名用可打印 ASCII 字符，含 `.wav` 最多 111 字符，列表最多显示 20 个文件。冷启动后按上述路径选曲，外层快门音类型显示 `CUS`。同名 WAV 换过内容时重新选一次。切回 A–E 可使用原厂快门声。

### 竖拍自动旋转

**文件** `portrait_video.wlm`。冷启动后原生功能自动接入，`Z8Mouldes` 里的 `Portrait video rotation` 是插件入口。

拍摄前先把机身转到所需的竖拍方向，再按录制。插件在第一帧记录方向，支持旋转信息的播放器会把成片正立显示，编码分辨率保持原样。录制中转动机身仍沿用开录方向。可以分别录两段相反方向的竖拍和一段横拍，在电脑上确认显示方向。r3 已有 1080p MOV 两个方向、横拍和一段 N-RAW NEV 的实机文件检查，其他组合按实际录制设置验证。

## 使用 Windows 调试工作台

1. 在仓库根目录用带 Tk 的 Python 3.11+ 安装主机依赖并启动窗口。

   ```powershell
   python -m pip install -r requirements-host.txt
   .\Start-Z8-Debug.cmd
   ```

2. 机内进入 **Fenestra**，激活后把 **USB Debug** 设为 `On`。插上数据线，点击工作台的「连接 Z8」。工作台可刷新状态、检查构建身份、运行 RTOS 命令、读取寄存器和内存。
3. 自动化也走同一个可见工作台。可以先运行 `python host/workbench_client.py workbench_status` 检查本地窗口，已连接相机时，可运行 `python host/workbench_client.py refresh --id z8-status-001`，在输出中核对 `build_identity`。每个操作使用独立的请求 ID。命令等待超时后用 `python host/workbench_client.py result --id z8-status-001` 查询同一请求。「调用记录」保存在本地。
4. 准备拍摄时断开工作台连接并拔下 USB。日常安装插件可用读卡器，工作台直接写卡需要匹配底座的本地原生调用配置。

## 常见情况

| 看到什么 | 怎么检查 |
| --- | --- |
| `Ready`，插件页面还没出现 | 在 Fenestra 按 `Activate`，再回到设定菜单打开 `Z8Mouldes`。 |
| `Active`，`Activate` 变灰 | 已激活，可直接使用插件。 |
| 替换文件后还是旧行为 | 核对启动卡和文件名，移走同名旧版或禁用副本，等写卡结束后做一次完整冷启动。 |
| 原厂菜单项出现，但 `Z8Mouldes` 还没展开 | 原生菜单项随冷启动装入，插件页在激活后显示。 |
| 选项显示「功能未准备完成」或「录制中，已锁定」 | 先停录、等文件写完，再核对底座、插件启用状态及对应的录像类型。 |
| `Card error` 或插件显示 `Invalid` | 记下完整错误码，检查卡槽、`FENESTRA/`、SHA-256 和同名文件。使用同一 Release 的插件组合。 |

## 功能来源与移植

部分 WLM 基于其他项目的功能实现移植开发。**画幅 / N-RAW、ProRes 品质、H.265 码率、Log 色彩、照片工具**使用 NikonFirmwarePatch **v0.4.0-rc.2** 的对应功能实现，本项目将它们适配为 Fenestra WLM，并接入本项目的模块界面和加载方式。[NikonFirmwarePatch 固定源码](https://github.com/XinmiaoZhao/NikonFirmwarePatch/tree/a21fc8c04b6dd863439c4192d387b755633287f6)

**卡内 WAV** 将 z8-card-wav **v0.1.1** 适配为 WLM，其快门声实现源自 s3lemming 的 Z9 卡内 WAV 方案。独立组件按各自的许可分发。[z8-card-wav v0.1.1](https://github.com/PIPA12344/z8-card-wav/releases/tag/v0.1.1) · [Z9 实现](https://github.com/s3lemming/z9-firmware-patch/tree/88a6f3e5195d7f38792dc8eddeb1526fde4096dc) · [来源与许可记录](../vendor/NikonFirmwarePatch-container/z8cardwav/NOTICE)

开发者可继续阅读[本地构建](z8-build.zh-CN.md)、[Z8 SDK](z8-sdk.md)和[模块开发](module-development.md)。
