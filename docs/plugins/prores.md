# ProRes 品质

**文件** `prores.wlm`，**入口** 设定菜单 → Z8Mouldes → ProRes 品质 → 品质。

配套 Nikon Z 8 C3.11 的 `cold-retry3`。复制到卡根目录的 `FENESTRA/` 后完整冷启动。[下载 prores.wlm](https://github.com/PIPA12344/Fenestra-Z8-C311-source/releases/download/wlm-2026.11.10-r10/prores.wlm) · [安装和停用](../z8-usage.zh-CN.md#安装插件)

## 选择 ProRes 档位

先把视频文件类型设为 **ProRes 422**，部分菜单中入口仍显示 **ProRes 422 HQ**。停止录制后在插件页选 HQ（默认）、标准（422）、LT 或 Proxy。档位影响 ProRes 422 的压缩和文件大小，沿用原有画幅和帧率。需要核对录制结果时，四档 MOV 编码标识依次为 `apch`、`apcn`、`apcs`、`apco`。

## 功能来源与移植

本插件使用 NikonFirmwarePatch v0.4.0-rc.2 的对应功能实现，并适配为 Fenestra WLM。[对应源码](https://github.com/XinmiaoZhao/NikonFirmwarePatch/tree/a21fc8c04b6dd863439c4192d387b755633287f6)
