# CourseMate

CourseMate 是面向大学生的课程学习助手：整理课程资料、检索知识与原题、回答问题，并保存个人学习记录。当前源码默认进入学习模式。

## 主要功能

- **课程资料**：添加公开课程网址，上传 PDF、Word、MD、TXT、HTML、ZIP；后台整理并保留来源。
- **知识问答**：导入 TXT / MD 学习资料，由单一 LangGraph Agent 检索、回答和检查答案。
- **原题查找**：按课程、知识点、年份、题型查找，显示原文、原图和出处；支持上传图片或文件找相似题。
- **我的学习**：手动标记做题状态，回看题目、参考解答和主要方法点。

## 本机运行

需要 Windows、Python 3.11+ 和可用的在线模型；无需运行本地大模型。已有开发环境时双击 `Start-Study-Demo.bat`，或执行：

```powershell
.venv\Scripts\python.exe -m aitown.cli ui --data study --port 8501
```

打开 <http://127.0.0.1:8501>。首次从源码配置环境：

```powershell
uv venv .venv --python 3.13
uv pip install --python .venv\Scripts\python.exe -e ".[dev,privacy,question-bank]"
.venv\Scripts\python.exe -m aitown.cli ui --data study --port 8501
```

本机可以使用当前 Windows 账户已登录的 Codex CLI / ChatGPT，也可以在设置中填写兼容模型 API。前者需要先安装并登录 Codex CLI；后者需要自己的模型服务地址和密钥。详见[学习功能](docs/STUDY.md)和[界面说明](docs/UI.md)。

## 使用流程

1. 添加公开课程或上传自己的资料，等待后台整理完成。
2. 选择课程，按知识点等条件查找内容，并通过原图和出处核对。
3. 自己完成练习，手动记录状态；需要时查看模型生成的参考解答与方法。
4. 在“我的学习”中回看记录。不选课程也可以进行普通知识问答。

## 数据与边界

本机题库和学习状态默认保存在 `data/question_bank/`、`data/runtime/ui-study/`，不随 Git 提交。当前问题、必要历史和候选资料可能发送给所选在线模型；仅导入允许这样使用的资料。学习模式不加载旧微信资料或个人画像。

扫描识别、复杂公式和题答配对可能需要人工核对。模型解答不是官方答案；当前没有自动判分、知识掌握度诊断或自动复习计划。详见[题库说明](docs/QUESTION_BANK.md)。

## 开发与部署

```powershell
.venv\Scripts\python.exe -m pytest -q
node scripts/verify_study_bootstrap.js
node scripts/verify_study_ui.js
```

主要代码在 `src/aitown/`，测试在 `tests/`，脚本在 `scripts/`。主对话图为 `context → intent → rag / skill → reflect`；课程资料整理由独立后台任务执行。参见[架构](docs/ARCHITECTURE.md)、[检索](docs/RETRIEVAL.md)和[技能](docs/SKILLS.md)。

Windows ECS 部署见[部署说明](docs/ECS_WINDOWS.md)。仓库包含源码和部署脚本；便携运行包需要另行构建，见[便携版说明](docs/PORTABLE.md)。
