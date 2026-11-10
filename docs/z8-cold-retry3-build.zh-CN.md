# 从官方 C3.11 构建 cold-retry3

`cold-retry3` 是 [七个功能 WLM](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/tag/wlm-2026.11.10) 共用的 Nikon Z 8 C3.11 底座。用于复现该底座的核心源码固定在 `cold-retry3-source` 标签。以下步骤在 Windows x64 上运行。

## 准备

1. 安装 Python 3.11 或以上。解压 Windows x64 的 LLVM **19.1.5** 归档，其中 `bin` 目录应包含 `clang.exe`、`ld.lld.exe`、`llvm-objcopy.exe` 和 `llvm-nm.exe`。[clang+llvm-19.1.5-x86_64-pc-windows-msvc.tar.xz](https://github.com/llvm/llvm-project/releases/download/llvmorg-19.1.5/clang%2Bllvm-19.1.5-x86_64-pc-windows-msvc.tar.xz)
2. 下载并解压尼康官方 **Z 8 C3.11**，得到 `Z_8_0311.bin`。它的大小为 99,051,117 字节，SHA-256 为 `d67413c2ede6b9ce8887175f20700bd9fbad2a973a4820968c45503d15d80d96`。[尼康下载中心](https://downloadcenter.nikonimglib.com/en/download/fw/606.html)
3. 克隆固定源码并准备 Python 环境。

```powershell
git clone --branch cold-retry3-source --single-branch https://github.com/PIPA12344/Fenestra-Z8-C311-source.git Fenestra-cold-retry3
cd Fenestra-cold-retry3
py -3 -m venv .venv
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r requirements-z8.txt
New-Item -ItemType Directory -Path inputs -Force
```

## 生成和校验

将官方 `Z_8_0311.bin` 放入 `inputs/`。把 `$llvm` 改成 LLVM 19.1.5 的实际 `bin` 目录，然后执行下列命令。

```powershell
$llvm = 'C:\Program Files\LLVM\bin'
& $py -B scripts/build_cold_retry3.py --firmware inputs/Z_8_0311.bin --llvm-bin $llvm
Get-FileHash -Algorithm SHA256 -LiteralPath build/cold-retry3/Z_8_0311.bin
```

脚本在本地校验官方包、提取 MAIN、编译原生 WLM 底座、独立校验核心，并用仓库内固定哈希的容器读写器重新封装。最后核对输出文件的 SHA-256。

| 核对项 | 预期 SHA-256 |
| --- | --- |
| 本地成品 `build/cold-retry3/Z_8_0311.bin` | `0a9cdd079ab09136982a7bbcb2f3c0ffbe64a12f79cff27d5d5a5da833d7ee43` |
| 编译后的 MAIN `build/cold-retry3/core/z8-core.main` | `0e0114267ef82caf78b7795a470192b434528ec0f4a8a6b031d1a003c4c63dfd` |
| 调试工作台显示的 `build_identity` | `f06231d84970cda74ff6afcdb2aad7d03f6fe0bc4a3ec76c15a9cfd40654579a` |

构建脚本只操作本地文件，固件输入和输出分开保存。重跑时用 `--output-dir build/cold-retry3-check` 指定一个新的目录。成品仍是实验底座，离线哈希一致仅验证构建结果。
