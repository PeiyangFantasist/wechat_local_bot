# wechat_host/bot.py
import itchat
from itchat.content import TEXT
import logging
import re
from datetime import datetime
from flask import Flask, render_template
from models import Session, ChatMessage
import threading
import time
import os
import webbrowser
from flask_cors import CORS
from ollama import chat
from ollama import ChatResponse

# 设置你要使用的模型
model_name = "deepseek-r1:14b"
def get_local_model_response(message: str) -> str:
    """本地调用大模型并获取回复"""
    response: ChatResponse = chat(model=model_name, messages=[
        {
            'role': 'user',
            'content': message,
        },
    ])
    return response.message.content

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__, static_folder='static')
CORS(app)

# 全局变量存储上下文
chat_contexts = {}

def save_message(sender_id, sender_name, message, reply):
    """保存聊天记录到数据库"""
    try:
        session = Session()
        chat_message = ChatMessage(
            sender_id=sender_id,
            sender_name=sender_name,
            message=message,
            reply=reply
        )
        session.add(chat_message)
        session.commit()
        session.close()
    except Exception as e:
        logger.error(f"保存消息失败: {str(e)}")

def remove_think_tags(reply):
    while "<think>" in reply:
        start = reply.find("<think>")
        end = reply.find("</think>") + len("</think>")
        if start != -1 and end != -1:
            reply = reply.replace(reply[start:end], "")
    return reply

def get_local_response(message, user_id):
    """调用本地模型获取回复"""
    try:
        # 获取用户上下文
        if user_id not in chat_contexts:
            chat_contexts[user_id] = []

        # 添加新消息到上下文
        chat_contexts[user_id].append({"role": "user", "content": message})

        # 保持上下文长度不超过5条消息
        if len(chat_contexts[user_id]) > 5:
            chat_contexts[user_id] = chat_contexts[user_id][-5:]

        # 准备系统消息
        system_message = {
            "role": "system information",
            "content": "在这里填写人设"
        }

        # 只取最新的一条用户消息
        latest_user_message = chat_contexts[user_id][-1]

        # 组合系统消息和最新的一条用户消息
        all_messages = [system_message, latest_user_message]

        # 将消息列表转换为字符串
        input_string = ""
        for msg in all_messages:
            input_string += f"{msg['role']}: {msg['content']}\n"

        # 调用本地模型获取回复
        reply = get_local_model_response(input_string)

        # 去除思考内容
        reply = remove_think_tags(reply)

        # 添加回复到上下文
        chat_contexts[user_id].append({"role": "assistant", "content": reply})

        # 添加额外的提示信息
        reply += f"[消息由本地大模型{model_name}生成，不代表本人观点]"

        return reply
    except Exception as e:
        logger.error(f"调用本地模型失败: {str(e)} 时间{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return f"调用本地模型失败: {str(e)} 时间{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

@itchat.msg_register([TEXT])
def handle_text(msg):
    """处理文本消息"""
    try:
        # 获取发送者信息
        username = msg['FromUserName']
        content = msg['Text']
        
        # 获取发送者昵称
        sender = itchat.search_friends(userName=username)
        sender_name = sender['NickName'] if sender else username
        
        logger.info(f"收到消息 - 发送者: {sender_name}, 内容: {content}")
        
        # 获取回复
        reply = get_local_response(content, username)
        
        # 保存消息记录
        save_message(username, sender_name, content, reply)
        
        # 发送回复
        logger.info(f"回复 {sender_name}: {reply}")
        return reply
        
    except Exception as e:
        logger.error(f"处理消息失败: {str(e)}")
        return "抱歉，我遇到了一些问题，请稍后再试。"

# Flask路由
@app.route('/')
def index():
    """渲染监控页面"""
    return render_template('index.html')

@app.route('/messages')
def get_messages():
    """获取所有聊天记录"""
    # 添加跨域访问头
    session = Session()
    messages = session.query(ChatMessage).order_by(ChatMessage.created_at.desc()).all()
    result = [{
        'id': msg.id,
        'sender_name': msg.sender_name,
        'message': msg.message,
        'reply': msg.reply,
        'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for msg in messages]
    session.close()
    return {'messages': result}

def run_flask():
    """运行Flask应用"""
    app.config['SECRET_KEY'] = 'your-secret-key-here'  # 添加密钥
    app.config['TEMPLATES_AUTO_RELOAD'] = True  # 启用模板自动重载
    app.run(
        host='127.0.0.1',  # 改为本地地址
        port=5000,
        debug=False,  # 关闭调试模式
        threaded=True
    )

def open_dashboard():
    """打开监控面板"""
    time.sleep(2)  # 等待Flask服务器启动
    webbrowser.open('http://127.0.0.1:5000')

def login_wechat():
    """微信登录函数"""
    try:
        # 删除所有可能的登录文件
        if os.path.exists('itchat.pkl'):
            os.remove('itchat.pkl')
            logger.info("删除旧的登录状态文件")

        # 尝试登录
        itchat.auto_login(
            hotReload=False,
            enableCmdQR=-2,  # 使用终端二维码，如果是Windows可以改为-1
            statusStorageDir='itchat.pkl',
            loginCallback=lambda: logger.info("登录成功"),
            exitCallback=lambda: logger.info("微信退出")
        )
        
        # 等待登录完成
        time.sleep(3)
        
        # 验证登录状态
        friends = itchat.get_friends()
        if friends:
            logger.info(f"登录验证成功，共有 {len(friends)} 个好友")
            # 登录成功后打开监控页面
            open_dashboard()
            return True
            
        logger.error("登录验证失败")
        return False
        
    except Exception as e:
        logger.error(f"登录过程出错: {str(e)}")
        return False

def main():
    """主函数"""
    try:
        # 启动Flask线程
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("监控服务器已启动")
        
        # 删除之前的浏览器线程启动代码
        # 尝试登录微信
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                if login_wechat():  # 登录成功后会自动打开监控页面
                    # 注册消息处理函数
                    @itchat.msg_register([TEXT])
                    def text_reply(msg):
                        return handle_text(msg)
                    
                    # 运行
                    logger.info("开始运行微信机器人...")
                    itchat.run(debug=True)
                    break
                else:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.info(f"等待 10 秒后进行第 {retry_count + 1} 次重试")
                        time.sleep(10)
            except Exception as e:
                logger.error(f"运行出错: {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    logger.info(f"等待 10 秒后进行第 {retry_count + 1} 次重试")
                    time.sleep(10)
        
        if retry_count >= max_retries:
            logger.error("多次尝试登录失败，程序退出")
            
    except Exception as e:
        logger.error(f"程序运行错误: {str(e)}")
    finally:
        logger.info("程序退出")

if __name__ == '__main__':
    try:
        # 确保使用最新版本的 itchat-uos
        if not hasattr(itchat, '__version__') or itchat.__version__ < '1.5.0':
            logger.warning("建议更新 itchat-uos 到最新版本")
        main()
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {str(e)}")
