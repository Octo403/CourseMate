# 当前源码与 Windows 构建

## 当前入口

当前工作区保留学习模式源码、主开发环境和最新 ECS 源码部署包。旧 preview ZIP、补丁及解压副本已清理；当前学习版的便携运行包尚未重新构建或发布。

本机双击 `Start-Study-Demo.bat`，或执行：

```powershell
.venv\Scripts\python.exe -m aitown.cli ui --data study --port 8501
```

打开 `http://127.0.0.1:8501`，在设置中使用当前账户的 ChatGPT 登录或兼容模型 API。见 [STUDY.md](STUDY.md)。

ECS 上传包为 `dist/ecs-windows/AnotherMe-ECS-Windows-Source.zip`，包含应用源码及部署脚本，不包含 Python、运行依赖或个人数据。服务器运行 `hosted-ui`，访客填写自己的模型 API；见 [ECS_WINDOWS.md](ECS_WINDOWS.md)。

```powershell
.venv\Scripts\python.exe scripts/build_ecs_windows.py
```

## 构建便携运行包

构建机需要 Windows x64、项目开发环境、uv 和独立提取的 LibreOffice。准备包含 `program/soffice.com` 的 LibreOffice 目录：

```powershell
.venv\Scripts\python.exe scripts/build_portable.py --libreoffice-dir C:\BuildTools\LibreOffice --output dist\AnotherMe-Study-Windows-x64
# 可选：--sevenzip-dir "C:\Program Files\7-Zip"
```

输出目录必须是新目录。脚本复制独立 Python、安装应用依赖，加入文档转换器、当前使用说明及原创虚构试题，检查实际导入与静态资源后生成 ZIP。可用 `--python-home` 指定独立 Python 安装目录；不能指定虚拟环境。`components.json` 记录该包实际依赖版本。

构建不复制项目 `.env`、已有 `data/`、微信导出、课程原件、模型权重或账户凭证。此前本机下载及临时转换器已清理，构建工具需要重新准备。

## 构建后使用与数据

完整解压新包后，双击 `Start.bat`；`Stop.bat` 停止当前副本，`Diagnose.bat` 检查运行依赖。首次启动创建 `user-data/`：

```text
解压目录/
  Start.bat / Stop.bat / Diagnose.bat
  launcher.py
  runtime/                  独立 Python 与依赖
  tools/libreoffice/        Word 转换器
  示例资料/                 原创虚构试题
  user-data/
    question_bank/          新资料、题库、study.sqlite3
    application/            学习会话、知识库、偏好
    desktop.json
    startup.log
```

ChatGPT 方式需要用户自己安装并登录 Windows Codex CLI，便携包不提供账户。模型 API 使用用户填写的地址、Key 和型号；本机加密保存与 Windows 账户绑定。ECS 的 Key 仅保留在服务器运行内存。

备份或更新其他已在使用的副本时，先停止服务并等待后台处理结束，再复制整个 `user-data/`。更新程序文件时保留该副本的数据。本次工作区清理不影响其他电脑或 ECS 数据。

## 验证

```powershell
.venv\Scripts\python.exe -m pytest -q
node scripts/verify_study_bootstrap.js
node scripts/verify_study_ui.js
```

生成便携 ZIP 后还需要实际解压、启动、导入资料、执行模型请求、停止并重启，以及检查桌面和窄屏界面。源码测试和构建成功不能替代新 ZIP 的运行验收；旧 preview 验收结果不作为当前学习版通过的证据。

DOC / DOCX 的字体、公式和分页可能与原件不同。包内 Word 转换使用独立临时配置并禁止宏，原件保留。当前功能与既有学习验证见 [STUDY.md](STUDY.md) 和 [学习验证](verification/study-20261012.md)。
