## README：使用本地 AI 搭建微信聊天机器人

### 1. 部署本地 AI
安装 [ollama](https://ollama.com/) 并下载开源模型
### 2. API
参考 https://pypi.org/project/ollama/ 给出的方法
### 3. 下载相关的依赖库
在终端键入
```
pip install -r requirements.txt
```
### 4. 配置
- 修改 `realbot.py` 中的 `model_name` 为你下载的模型名称
- `system_message` 里的 `content` 修改为你的系统提示词
### 5. 运行
运行 `realbot.py` 会保存二维码到 `QR.png`，用微信扫描登录即可
