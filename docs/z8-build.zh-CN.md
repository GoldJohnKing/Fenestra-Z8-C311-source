# Z8 C3.11 本地构建

使用 Release 的七个 WLM 时，可按[使用手册](z8-usage.zh-CN.md#准备底座)应用预编译补丁，或从固定源码重建精确的 `cold-retry3`。以下命令供开发者构建其他本地配置。先准备 Python 3.11+ 和 LLVM，将 `clang`、`ld.lld`、`llvm-objcopy`、`llvm-nm` 加入 PATH，再用官方 C3.11 提取无 CRC MAIN。固件包和 MAIN 都会校验 SHA-256。[尼康原始文件](https://download.nikonimglib.com/archive8/wP5Vr003qbpC07ibhJ666rmRfF47/Z_8_0311.bin)

```sh
python -m pip install -r requirements-z8.txt
python fenestra_z8.py extract --firmware inputs/Z_8_0311.bin --external-project vendor/NikonFirmwarePatch-container --output inputs/z8-c311-main.bin
```

## 底座

第一条编译并离线验证普通底座。后两种配置分别带 ProRes 后端或通用原生 WLM 加载器，选项互斥。

```sh
python fenestra.py build --target z8-c311 --firmware inputs/z8-c311-main.bin --output build/local-core
python host/build_z8_core.py --firmware inputs/z8-c311-main.bin --prores-backend --output-dir build/local-prores-core
python host/build_z8_core.py --firmware inputs/z8-c311-main.bin --native-capsules --output-dir build/local-native-core
python host/verify_z8_core.py --firmware inputs/z8-c311-main.bin --build build/local-native-core --output build/local-native-core/verification.json
```

如需离线研究普通底座的密文补丁封装，可用以下命令在本地生成。补丁生成步骤只操作文件。

```sh
python fenestra.py make-patch --target z8-c311 --firmware inputs/Z_8_0311.bin --external-project vendor/NikonFirmwarePatch-container --work build/local-package --output build/local-z8.fxpatch
```

## 原生 WLM

取 [NikonFirmwarePatch v0.4.0-rc.2](https://github.com/XinmiaoZhao/NikonFirmwarePatch/releases/tag/v0.4.0-rc.2) 的 `NikonFirmwarePatch-v0.4.0-rc.2-toolkit.zip`，保存到本地 `inputs/`。下列脚本校验压缩包和所需成员的哈希，然后提取到本地 vendor 子目录。此工具包及预编译补丁单元由 NikonFirmwarePatch 项目提供，按该项目的许可使用。

```sh
python scripts/prepare_z8_feature_toolkit.py inputs/NikonFirmwarePatch-v0.4.0-rc.2-toolkit.zip
```

原生 WLM 将功能前端与对应的原生组件打包。以下是 PowerShell 示例，将 `$llvm` 换成包含 LLVM 工具的目录。

```powershell
$llvm = 'C:/path/to/LLVM/bin'
python nativepacks/wlm_controls/build.py --llvm $llvm --out build/local-controls
python nativepacks/wlm_controls/build.py --component locale --llvm $llvm --text-count 3225 --languages 36 --offsets-directory 0x4327c5a0 --pools-directory 0x439daf58 --out build/local-controls/locale
python host/build_wlm_native_components.py --stock inputs/z8-c311-main.bin --controls build/local-controls --out build/local-catalog
python host/package_wlm_native_components.py --catalog build/local-catalog --out build/local-components
foreach ($id in 'framing', 'prores', 'h265', 'log_colour', 'photo_tools') {
    $source = if ($id -eq 'photo_tools') { "modules/$id/module.c" } else { "examples/$id/module.c" }
    python fenestra_z8.py build-module $source --id $id --optimize s --llvm-bin $llvm --output-dir "build/local-frontends/$id"
}
python host/package_z8_wlm_plugins.py --components build/local-components --frontends build/local-frontends --output build/local-plugins
```

目录参数都使用新路径。组件构建会用原厂输入和选定配方独立核对语言表地址。五个生成的 WLM 分别输出到 `build/local-plugins/FENESTRA/`。画幅、ProRes、H.265 和 Log 色彩使用 Windows x64 LLVM 19.1.5 和 `--optimize s` 重建时，可得到当前 Release 对应的文件。此步骤的照片工具是用于下一步的基础包。

卡内 WAV 和竖拍 MOV 的构建脚本位于 `host/build_z8_card_wav.py` 与 `host/build_z8_portrait_video.py`。它们需要经过哈希校验的 cold-retry3 底座 MAIN。按 [cold-retry3 源码重编说明](z8-usage.zh-CN.md#从源码重新编译) 生成 `build/cold-retry3/core/z8-core.main`。

## 照片工具 r10

准备上节的 NikonFirmwarePatch 工具包及原厂 C3.11 MAIN。先按上节构建基础包 `build/local-plugins/FENESTRA/photo_tools.wlm`，再用 Windows x64 LLVM **19.1.5** 构建 r10。

```powershell
python -B host/build_photo_tools_r10.py --stock inputs/z8-c311-main.bin --base-wlm build/local-plugins/FENESTRA/photo_tools.wlm --llvm-bin $llvm --output-dir build/local-photo-tools-r10
```

产物为 `build/local-photo-tools-r10/photo_tools.wlm`。脚本验证源生成的原生代码与最终 WLM，最终 SHA-256 应为 `1f1cf2016022410df03fe910df725e0639f0ed8bafc491e47e3d6428e0eea38f`。使用方法见[照片工具](plugins/photo_tools.md)。

## Windows 调试工作台

```powershell
python -m pip install -r requirements-host.txt
.\Start-Z8-Debug.cmd
```

使用可见工作台连接，RTOS、内存和 Linux 操作都在“调用记录”页留下本地记录。可用 `python host/workbench_client.py --help` 查看同一个工作台的自动化入口。等待超时后用原请求 ID 查询结果，以免重复执行。Linux RAM 代理需要另外本地构建。

直接写相机卡的入口要求用户另行提供适配该核心身份和调用前置字节的可信配置。普通卡片复制可通过读卡器完成。
