# Z8 C3.11 本地构建

先按 [README](../README.md) 准备 LLVM、Python 依赖和原厂 C3.11 包。下列命令使用从原厂包提取的无 CRC MAIN。固件包与 MAIN 都有固定的完整 SHA-256，其他版本需要独立适配。

## 底座

普通底座由 README 中的 `fenestra.py build` 编译并离线验证。要编译带 ProRes 后端或带通用原生 WLM 加载器的底座，分别运行以下命令。选项互斥。

```sh
python host/build_z8_core.py --firmware inputs/z8-c311-main.bin --prores-backend --output-dir build/local-prores-core
python host/build_z8_core.py --firmware inputs/z8-c311-main.bin --native-capsules --output-dir build/local-native-core
python host/verify_z8_core.py --firmware inputs/z8-c311-main.bin --build build/local-native-core --output build/local-native-core/verification.json
```

如需离线研究普通底座的密文补丁封装，可用以下命令在本地生成。补丁生成步骤只操作文件。

```sh
python fenestra.py make-patch --target z8-c311 --firmware inputs/Z_8_0311.bin --external-project vendor/NikonFirmwarePatch-container --work build/local-package --output build/local-z8.fxpatch
```

## 原生 WLM

取 [NikonFirmwarePatch v0.4.0-rc.2](https://github.com/XinmiaoZhao/NikonFirmwarePatch/releases/tag/v0.4.0-rc.2) 的 `NikonFirmwarePatch-v0.4.0-rc.2-toolkit.zip`，保存到本地 `inputs/`。下列脚本校验压缩包和所需成员的哈希，然后提取到本地 vendor 子目录。此依赖及其预编译补丁单元由上游提供，许可仍由上游决定。

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
    python fenestra_z8.py build-module $source --id $id --llvm-bin $llvm --output-dir "build/local-frontends/$id"
}
python host/package_z8_wlm_plugins.py --components build/local-components --frontends build/local-frontends --output build/local-plugins
```

目录参数都使用新路径。组件构建会用原厂输入和选定配方独立核对语言表地址。五个生成的 WLM 分别输出到 `build/local-plugins/FENESTRA/`。

卡内 WAV 和竖拍 MOV 的构建脚本位于 `host/build_z8_card_wav.py` 与 `host/build_z8_portrait_video.py`。它们需要经过哈希校验的 cold-retry3 底座 MAIN。按 [cold-retry3 复建说明](z8-cold-retry3-build.zh-CN.md) 生成 `build/cold-retry3/core/z8-core.main`。

## Windows 调试工作台

```powershell
python -m pip install -r requirements-host.txt
.\Start-Z8-Debug.cmd
```

使用可见工作台连接，RTOS、内存和 Linux 操作都在“调用记录”页留下本地记录。可用 `python host/workbench_client.py --help` 查看同一个工作台的自动化入口。等待超时后用原请求 ID 查询结果，以免重复执行。Linux RAM 代理需要另外本地构建。

直接写相机卡的入口要求用户另行提供适配该核心身份和调用前置字节的可信配置。普通卡片复制可通过读卡器完成。
