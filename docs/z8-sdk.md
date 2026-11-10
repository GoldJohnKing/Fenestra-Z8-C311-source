# Z8 C3.11 主机和 SDK

原生只读接口见 [Native profile probe](../examples/native_probe/README.md)。

完整核心和 SDK 共用 canonical target z8-c311，平台表包含 80 个命名原厂函数与 5 张表。SDK 使用完整目标，不把最小诊断原型当成模块加载器。

WLM target、FXI1 application 和 module-target 均为无 CRC MAIN 的 SHA-256：2b43a31c9de838f84b12416de4348a7004e65be07f853ec56ec2b10f3a8e3853。原厂包与带 CRC 组件的摘要另用于输入验证，不能替代模块身份。

~~~powershell
python fenestra_z8.py build-module examples/prores/module.c --id prores --output-dir build/my-prores
~~~

保留标准 ELF 分段、重定位、入口 ABI、堆栈和能力检查。生成 WLM 不需要原厂固件或密钥。为其他型号构建的插件仍被拒绝。完整核心从 A:\FENESTRA\ 发现 .wlm；.wlm.disabled 不加载。自动激活默认关闭。

主机 profile 只接受型号 Z 8/Z8 与 3.11/V3.11；实际 FXI1 还要核对 Nikon Z8、固件代码 311、应用身份与模块目标。导入主机模块不打开相机。

机内启用 Fenestra 和 USB Debug 后，从可见工作台连接。自动化入口见 `python host/workbench_client.py --help`。

目前仍为完整功能开发版。上游明确提示现版存在变砖风险；本地构建与模拟结果不能代替实体 USB、冷暖启动和正常关机验收。状态与具体证据见 [项目说明](../README.md)。
