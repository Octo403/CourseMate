# 当前学习界面

## 启动与入口

双击项目根目录的 `Start-Study-Demo.bat`，或执行：

```powershell
.venv\Scripts\python.exe -m aitown.cli ui --data study --port 8501
```

打开 `http://127.0.0.1:8501`。本机支持当前 Windows 账户已登录的 Codex CLI / ChatGPT，或用户填写的模型 API。云端使用独立的 `hosted-ui` 入口，访客填写自己的 API；见 [ECS 部署](ECS_WINDOWS.md)。

首页入口为“课程资料”“我的学习”“设置”。学习模式隐藏个人资料、微信同步、本机模型和表达画像入口。全部延后加载的脚本完成后才请求初始数据，避免首次显示旧个人界面。

## 操作

1. 在“设置”选择连接并测试。所选在线模型参与意图理解、对话、知识重排、自省和题库处理。
2. 直接聊天、解释知识或计算；“设置 → 知识资料”可导入 TXT / MD，作为独立学习知识库。
3. 打开“课程资料”，收集公开课程、上传资料或添加网址，查看逐文件进度。
4. 通过 `@ 题库` 选择课程，再输入找题要求。课程选择只限定找题范围。
5. 用“＋”上传参考题，或粘贴图片、拖入文件；附件仅用于本轮找相似题。
6. 完成原题后手动标记“未做过 / 做过 / 做对 / 做错”；查看解答不改变标记。
7. 点击“解答与方法”获取书面参考解答与一个主要方法点，按需查看图解。
8. 在“我的学习”按状态浏览保留题目、解答和方法。

匹配说明、方法细节及参考题识别结果默认折叠。处理时展示简短阶段进度，完成后隐藏；学习页面不展示开发调试 JSON 或初稿。Enter 发送，Shift+Enter 换行。

## 数据与清理后的首次使用

工作区的旧课程、题库、做题记录、微信导出及派生资料、会话、偏好和索引已清理。首次运行重新创建空的 `data/question_bank/` 与 `data/runtime/ui-study/`，需要重新导入资料和设置连接。源码与部署包仅包含虚构示例，不带已收集的课程库。

ECS 通过浏览器 Cookie 区分独立空间，学习资料保存在服务器。清除 Cookie 后不能自动找回旧空间；API Key 仅保留在运行内存，重启或空间回收后需要重填。

## 可选个人资料实验

源码保留个人资料相关实现与测试，需要显式选择 `--data synthetic`、`--data wechat` 或 `--data configured`。默认学习模式不启用这些入口。此前微信库、派生索引及模型权重已经删除，旧配置路径不代表文件仍存在。

合成模式可重新创建虚构数据：

```powershell
.venv\Scripts\python.exe -m aitown.cli --mode demo ui --data synthetic --port 8503
```

使用实际个人资料需要重新提供有效数据与显式范围。见 [微信同步实现](WECHAT_SYNC.md)、[资料管线](DATA_PIPELINE.md) 和 [风格实现](STYLE.md)。

## 验证

```powershell
.venv\Scripts\python.exe -m pytest -q
node scripts/verify_study_bootstrap.js
node scripts/verify_study_ui.js
```

启动顺序验证覆盖延迟加载学习脚本、云端 API 引导、刷新后禁用服务器 ChatGPT 登录、本机模式及显式合成模式。DOM 和接口测试不替代浏览器视觉验收；模型解答仍需核对。
