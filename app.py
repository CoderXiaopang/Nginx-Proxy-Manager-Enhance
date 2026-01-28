# -*- coding: utf-8 -*-
"""
NPM Meta - Nginx Proxy Manager 增强管理工具
对接 Nginx Proxy Manager API，提供带备注的端口转发管理功能

GitHub: https://github.com/CoderXiaopang/Nginx-Proxy-Manager-Enhance
"""
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
import sqlite3
import os
from functools import wraps
from datetime import timedelta

# 尝试加载 .env 文件（可选依赖）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 未安装时跳过

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.permanent_session_lifetime = timedelta(days=7)  # session 有效期 7 天

# NPM 配置 - 从环境变量读取
NPM_HOST = os.environ.get('NPM_HOST', 'localhost:81')
NPM_BASE_URL = f"http://{NPM_HOST}/api"
DB_NAME = "npm_meta.db"


# ==================== 数据库初始化 ====================
def init_db():
    """初始化 SQLite 数据库"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS streams 
                       (npm_id INTEGER PRIMARY KEY, 
                        memo TEXT,
                        doc_url TEXT,
                        test_url TEXT,
                        repo_url TEXT)''')
        print("✅ 数据库初始化完成")


# ==================== 装饰器：登录验证 ====================
def login_required(f):
    """装饰器：检查用户是否已登录"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'token' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== NPM API 封装 ====================
def npm_login(email, password):
    """调用 NPM 登录接口获取 Token"""
    url = f"{NPM_BASE_URL}/tokens"
    payload = {"identity": email, "secret": password}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            return {"success": True, "token": r.json()['token']}
        else:
            return {"success": False, "error": f"登录失败: {r.json().get('message', '未知错误')}"}
    except Exception as e:
        return {"success": False, "error": f"网络错误: {str(e)}"}


def npm_get_streams(token):
    """获取所有端口转发列表"""
    url = f"{NPM_BASE_URL}/nginx/streams"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return {"success": True, "data": r.json()}
        else:
            return {"success": False, "error": "获取列表失败"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def npm_create_stream(token, incoming_port, forward_ip, forward_port):
    """创建端口转发"""
    url = f"{NPM_BASE_URL}/nginx/streams"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "incoming_port": int(incoming_port),
        "forwarding_host": forward_ip,
        "forwarding_port": int(forward_port),
        "tcp_forwarding": True,
        "udp_forwarding": False,
        "certificate_id": 0,  # 新增：证书ID，0表示不使用
        "meta": {}  # 新增：元数据，默认为空对象
    }
    try:
        print(f"🔌 发送请求到 NPM: {url}")
        print(f"📦 请求payload: {payload}")
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"📡 NPM响应状态码: {r.status_code}")
        print(f"📡 NPM响应内容: {r.text}")

        if r.status_code in [200, 201]:
            return {"success": True, "data": r.json()}
        else:
            # 尝试解析错误信息
            try:
                error_detail = r.json()
                error_msg = error_detail.get('error', {}).get('message', str(error_detail))
            except:
                error_msg = r.text
            return {"success": False, "error": f"创建失败 ({r.status_code}): {error_msg}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def npm_delete_stream(token, stream_id):
    """删除端口转发"""
    url = f"{NPM_BASE_URL}/nginx/streams/{stream_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        print(f"🗑️ 正在删除 Stream ID: {stream_id}")
        print(f"🔗 请求URL: {url}")

        r = requests.delete(url, headers=headers, timeout=10)

        print(f"📡 删除响应状态码: {r.status_code}")
        print(f"📡 删除响应内容: {r.text}")

        if r.status_code == 200:
            # NPM 返回的是布尔值 true
            return {"success": True}
        elif r.status_code == 204:
            # 无内容也是成功
            return {"success": True}
        elif r.status_code == 404:
            return {"success": False, "error": "端口转发规则不存在或已被删除"}
        elif r.status_code == 403:
            return {"success": False, "error": "没有权限删除此规则"}
        else:
            try:
                error_detail = r.json()
                error_msg = error_detail.get('error', {}).get('message', str(error_detail))
            except:
                error_msg = r.text or f"未知错误 (状态码: {r.status_code})"
            return {"success": False, "error": error_msg}

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"网络请求失败: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"系统错误: {str(e)}"}

# ==================== 数据库操作 ====================
def save_memo(npm_id, memo, doc_url='', test_url='', repo_url=''):
    """保存备注和URL到数据库"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""INSERT OR REPLACE INTO streams 
                       (npm_id, memo, doc_url, test_url, repo_url) 
                       VALUES (?, ?, ?, ?, ?)""",
                     (npm_id, memo, doc_url, test_url, repo_url))


def get_memo(npm_id):
    """获取单个备注"""
    with sqlite3.connect(DB_NAME) as conn:
        result = conn.execute("SELECT memo FROM streams WHERE npm_id = ?", (npm_id,)).fetchone()
        return result[0] if result else None


def get_all_memos():
    """获取所有备注和URL（返回字典）"""
    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute("SELECT npm_id, memo, doc_url, test_url, repo_url FROM streams").fetchall()
        return {row[0]: {'memo': row[1], 'doc_url': row[2], 'test_url': row[3], 'repo_url': row[4]} for row in rows}


def delete_memo(npm_id):
    """删除备注"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM streams WHERE npm_id = ?", (npm_id,))


# ==================== 路由：页面 ====================
@app.route('/')
def login_page():
    """登录页面"""
    return render_template('loginh.html')


@app.route('/manage')
@login_required
def manage_page():
    """管理页面（需要登录）"""
    return render_template('memang.html')


# ==================== 路由：API ====================
@app.route('/api/login', methods=['POST'])
def api_login():
    """登录接口"""
    data = request.json
    email = data.get('username')  # 前端字段是 username
    password = data.get('password')
    
    if not email or not password:
        return jsonify({"success": False, "error": "账号密码不能为空"}), 400
    
    # 调用 NPM 登录
    result = npm_login(email, password)
    if result['success']:
        # 登录成功，保存 token 到 session
        session.permanent = data.get('rememberMe', False)  # 是否记住登录
        session['token'] = result['token']
        session['email'] = email
        return jsonify({"success": True, "message": "登录成功"})
    else:
        return jsonify(result), 401


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """登出接口"""
    session.clear()
    return jsonify({"success": True})


@app.route('/api/streams', methods=['GET'])
@login_required
def api_get_streams():
    """获取端口转发列表（带备注）"""
    token = session.get('token')
    
    # 从 NPM 获取数据
    npm_result = npm_get_streams(token)
    if not npm_result['success']:
        return jsonify(npm_result), 500
    
    # 获取本地备注和URL
    memos = get_all_memos()
    
    # 合并数据
    streams = npm_result['data']
    for stream in streams:
        stream_data = memos.get(stream['id'], {})
        stream['memo'] = stream_data.get('memo', '') if isinstance(stream_data, dict) else ''
        stream['doc_url'] = stream_data.get('doc_url', '') if isinstance(stream_data, dict) else ''
        stream['test_url'] = stream_data.get('test_url', '') if isinstance(stream_data, dict) else ''
        stream['repo_url'] = stream_data.get('repo_url', '') if isinstance(stream_data, dict) else ''
    
    return jsonify({"success": True, "data": streams})


@app.route('/api/streams', methods=['POST'])
@login_required
def api_create_stream():
    """创建端口转发"""
    try:
        token = session.get('token')
        data = request.json

        print(f"📥 收到前端数据: {data}")  # 添加这行

        incoming_port = data.get('incoming_port')
        forward_ip = data.get('forward_ip')
        forward_port = data.get('forward_port')
        memo = data.get('memo', '')
        doc_url = data.get('doc_url', '')
        test_url = data.get('test_url', '')
        repo_url = data.get('repo_url', '')

        # 验证参数
        if not all([incoming_port, forward_ip, forward_port]):
            return jsonify({"success": False, "error": "参数不完整"}), 400

        # 验证端口范围
        if not (1 <= int(incoming_port) <= 65535) or not (1 <= int(forward_port) <= 65535):
            return jsonify({"success": False, "error": "端口号必须在 1-65535 之间"}), 400

        # 调用 NPM 创建
        result = npm_create_stream(token, incoming_port, forward_ip, forward_port)

        if result['success']:
            npm_id = result['data']['id']
            save_memo(npm_id, memo, doc_url, test_url, repo_url)
            return jsonify({"success": True, "message": "创建成功", "data": result['data']})
        else:
            return jsonify(result), 500

    except Exception as e:
        print(f"❌ 创建转发异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"服务器错误: {str(e)}"}), 500


@app.route('/api/streams/<int:stream_id>', methods=['DELETE'])
@login_required
def api_delete_stream(stream_id):
    """删除端口转发"""
    token = session.get('token')

    print(f"📝 收到删除请求: stream_id={stream_id}")

    # 先调用 NPM 删除
    result = npm_delete_stream(token, stream_id)

    if result['success']:
        # NPM 删除成功，再删除本地备注
        delete_memo(stream_id)
        print(f"✅ 删除成功: stream_id={stream_id}")
        return jsonify({"success": True, "message": "删除成功"})
    else:
        # NPM 删除失败，返回具体错误
        print(f"❌ 删除失败: {result['error']}")
        return jsonify(result), 500


# ==================== 主程序入口 ====================
if __name__ == '__main__':
    # 初始化数据库
    init_db()
    
    print("=" * 60)
    print("🚀 NPM Meta - Nginx Proxy Manager 增强管理工具")
    print(f"📍 访问地址: http://127.0.0.1:5001")
    print(f"🔗 NPM 服务器: {NPM_HOST}")
    print("=" * 60)
    
    # 启动 Flask 应用
    app.run(debug=True, host='0.0.0.0', port=5001)

