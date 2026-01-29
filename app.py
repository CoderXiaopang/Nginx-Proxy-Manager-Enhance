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
import threading
import time
import socket


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

# 后台健康检查用的管理员账号（可选）
NPM_ADMIN_EMAIL = os.environ.get('NPM_ADMIN_EMAIL', '')
NPM_ADMIN_PASSWORD = os.environ.get('NPM_ADMIN_PASSWORD', '')


# 全局变量：存储健康状态
# {stream_id: {"status": "ok"|"error"|"unknown", "msg": "...", "last_check": timestamp}}
STREAM_HEALTH_STATUS = {}



# ==================== 数据库初始化 ====================
def init_db():
    """初始化 SQLite 数据库"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS streams 
                       (npm_id INTEGER PRIMARY KEY, 
                        memo TEXT,
                        doc_url TEXT,
                        test_url TEXT,
                        repo_url TEXT,
                        health_status TEXT DEFAULT 'unknown',
                        health_msg TEXT DEFAULT 'Pending...',
                        health_last_check REAL)''')
        
        # 检查是否需要添加新字段（兼容旧数据库）
        cursor = conn.execute("PRAGMA table_info(streams)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'health_status' not in columns:
            conn.execute("ALTER TABLE streams ADD COLUMN health_status TEXT DEFAULT 'unknown'")
        if 'health_msg' not in columns:
            conn.execute("ALTER TABLE streams ADD COLUMN health_msg TEXT DEFAULT 'Pending...'")
        if 'health_last_check' not in columns:
            conn.execute("ALTER TABLE streams ADD COLUMN health_last_check REAL")
        
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


def npm_update_stream(token, stream_id, incoming_port, forward_ip, forward_port):
    """更新端口转发"""
    url = f"{NPM_BASE_URL}/nginx/streams/{stream_id}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "incoming_port": int(incoming_port),
        "forwarding_host": forward_ip,
        "forwarding_port": int(forward_port),
        "tcp_forwarding": True,
        "udp_forwarding": False,
        "certificate_id": 0,
        "meta": {}
    }
    try:
        print(f"✏️ 更新 Stream ID: {stream_id}")
        print(f"📦 更新 payload: {payload}")
        r = requests.put(url, json=payload, headers=headers, timeout=10)
        print(f"📡 更新响应状态码: {r.status_code}")
        print(f"📡 更新响应内容: {r.text}")

        if r.status_code in [200, 201]:
            return {"success": True, "data": r.json()}
        else:
            try:
                error_detail = r.json()
                error_msg = error_detail.get('error', {}).get('message', str(error_detail))
            except:
                error_msg = r.text
            return {"success": False, "error": f"更新失败 ({r.status_code}): {error_msg}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def npm_toggle_stream(token, stream_id, enabled):
    """切换端口转发启用状态"""
    url = f"{NPM_BASE_URL}/nginx/streams/{stream_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # 先获取当前 stream 信息
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return {"success": False, "error": "获取转发信息失败"}
        
        current_data = r.json()
        print(f"📋 当前 stream 数据: {current_data}")
        
        # 构建更新 payload，只包含 NPM 允许的字段
        payload = {
            "incoming_port": current_data['incoming_port'],
            "forwarding_host": current_data['forwarding_host'],
            "forwarding_port": current_data['forwarding_port'],
            "tcp_forwarding": current_data.get('tcp_forwarding', True),
            "udp_forwarding": current_data.get('udp_forwarding', False),
            "certificate_id": current_data.get('certificate_id', 0),
            "meta": current_data.get('meta', {})
        }
        
        print(f"🔄 切换 Stream {stream_id} 状态: enabled={enabled}")
        print(f"📦 发送 payload: {payload}")
        
        # 使用 NPM 的 enable/disable 专用接口（如果有的话）
        # 或者用 PUT 更新完整数据
        if enabled:
            # 启用：发送 POST 到 enable 接口
            enable_url = f"{NPM_BASE_URL}/nginx/streams/{stream_id}/enable"
            r = requests.post(enable_url, headers=headers, timeout=10)
        else:
            # 禁用：发送 POST 到 disable 接口
            disable_url = f"{NPM_BASE_URL}/nginx/streams/{stream_id}/disable"
            r = requests.post(disable_url, headers=headers, timeout=10)
        
        print(f"📡 切换响应: {r.status_code} - {r.text}")

        if r.status_code in [200, 201]:
            return {"success": True, "data": r.json() if r.text else {}}
        else:
            try:
                error_detail = r.json()
                error_msg = error_detail.get('error', {}).get('message', str(error_detail))
            except:
                error_msg = r.text or f"状态码: {r.status_code}"
            return {"success": False, "error": f"切换失败: {error_msg}"}
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

        return {"success": False, "error": f"系统错误: {str(e)}"}


# ==================== 健康检查逻辑 ====================
def check_stream_connectivity(forward_ip, forward_port):
    """
    检查连通性:
    1. 优先尝试 http://ip:port/health
    2. 失败则尝试简单的 TCP 连接
    """
    # 1. 尝试 /health 接口
    try:
        url = f"http://{forward_ip}:{forward_port}/health"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            try:
                # 尝试解析 JSON
                data = r.json()
                if data.get("status") == "ok":
                    return {"status": "ok", "msg": "Health check ok"}
            except:
                pass
            # 即使没有 status: ok，只要 200 也算通
            return {"status": "ok", "msg": f"HTTP {r.status_code}"}
    except:
        # HTTP 失败，忽略，尝试 TCP
        pass

    # 2. 尝试 TCP 连接 (curl host:port 这里简化为 connect 成功即可)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((forward_ip, int(forward_port)))
        sock.close()
        
        if result == 0:
            return {"status": "ok", "msg": "TCP connect success"}
        else:
            return {"status": "error", "msg": f"TCP error code: {result}"}
    except Exception as e:
        return {"status": "error", "msg": f"Check error: {str(e)}"}


def save_health_status(npm_id, status, msg):
    """保存健康状态到数据库"""
    with sqlite3.connect(DB_NAME) as conn:
        # 先确保记录存在
        conn.execute("INSERT OR IGNORE INTO streams (npm_id) VALUES (?)", (npm_id,))
        # 更新健康状态
        conn.execute("""UPDATE streams 
                       SET health_status = ?, health_msg = ?, health_last_check = ?
                       WHERE npm_id = ?""",
                     (status, msg, time.time(), npm_id))


def get_health_status(npm_id):
    """从数据库获取健康状态"""
    with sqlite3.connect(DB_NAME) as conn:
        result = conn.execute(
            "SELECT health_status, health_msg, health_last_check FROM streams WHERE npm_id = ?",
            (npm_id,)
        ).fetchone()
        if result:
            return {
                'status': result[0] or 'unknown',
                'msg': result[1] or 'Pending...',
                'last_check': result[2]
            }
        return {'status': 'unknown', 'msg': 'Pending...', 'last_check': None}


def health_check_daemon(app):
    """后台线程：定时检查所有转发的健康状态"""
    with app.app_context():
        print("🚑 健康检查线程已启动...")
        
        # 尝试获取后台管理员 token
        bg_token = None
        if NPM_ADMIN_EMAIL and NPM_ADMIN_PASSWORD:
            print("🔑 使用管理员账号登录 NPM...")
            login_result = npm_login(NPM_ADMIN_EMAIL, NPM_ADMIN_PASSWORD)
            if login_result['success']:
                bg_token = login_result['token']
                print("✅ 后台管理员登录成功")
            else:
                print(f"❌ 后台管理员登录失败: {login_result.get('error')}")
        
        # 🔥 立即执行第一次检查
        def run_health_check():
            try:
                # 优先使用后台 token 获取最新数据
                streams_to_check = []
                
                if bg_token:
                    # 使用后台管理员账号获取流列表
                    result = npm_get_streams(bg_token)
                    if result['success']:
                        streams_to_check = result['data']
                        print(f"📡 从 NPM 获取到 {len(streams_to_check)} 个流")
                else:
                    # 降级：使用缓存的数据
                    global CACHED_STREAMS
                    if 'CACHED_STREAMS' in globals() and CACHED_STREAMS:
                        streams_to_check = CACHED_STREAMS
                        print(f"📦 使用缓存数据，共 {len(streams_to_check)} 个流")
                
                if not streams_to_check:
                    print("⚠️  没有可检查的流（请配置 NPM_ADMIN_EMAIL 和 NPM_ADMIN_PASSWORD，或等待用户访问页面）")
                    return
                
                # 执行健康检查
                checked_count = 0
                for stream in streams_to_check:
                    sid = stream.get('id')
                    ip = stream.get('forwarding_host')
                    port = stream.get('forwarding_port')
                    
                    if ip and port:
                        res = check_stream_connectivity(ip, port)
                        # 保存到数据库
                        save_health_status(sid, res['status'], res['msg'])
                        # 同时更新内存缓存（可选，用于快速访问）
                        STREAM_HEALTH_STATUS[sid] = {
                            "status": res['status'],
                            "msg": res['msg'],
                            "last_check": time.time()
                        }
                        checked_count += 1
                
                print(f"✅ 健康检查完成，检查了 {checked_count} 个服务")
            except Exception as e:
                print(f"❌ Health check error: {e}")
                import traceback
                traceback.print_exc()
        
        # 等待2秒让应用完全启动
        time.sleep(2)
        print("🔍 开始首次健康检查...")
        run_health_check()
        
        # 定时检查
        while True:
            time.sleep(60)  # 每隔 1 分钟
            print("🔄 执行定时健康检查...")
            run_health_check()




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
    """登录接口 - 支持 JSON 和表单提交两种方式"""
    # 判断请求类型：JSON 或表单
    if request.is_json:
        data = request.json
        email = data.get('username')
        password = data.get('password')
        remember_me = data.get('rememberMe', False)
        is_form_submit = False
    else:
        # 表单提交
        email = request.form.get('username')
        password = request.form.get('password')
        remember_me = request.form.get('rememberMe') == 'on'
        is_form_submit = True

    if not email or not password:
        if is_form_submit:
            return redirect('/?error=' + requests.utils.quote("账号密码不能为空"))
        return jsonify({"success": False, "error": "账号密码不能为空"}), 400

    # 调用 NPM 登录
    result = npm_login(email, password)
    if result['success']:
        # 登录成功，保存 token 到 session
        session.permanent = remember_me  # 是否记住登录
        session['token'] = result['token']
        session['email'] = email

        if is_form_submit:
            # 表单提交：重定向到管理页面（触发浏览器密码保存提示）
            return redirect('/manage')
        return jsonify({"success": True, "message": "登录成功"})
    else:
        if is_form_submit:
            # 表单提交失败：重定向回登录页并显示错误
            return redirect('/?error=' + requests.utils.quote(result.get('error', '登录失败')))
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
    
    # 缓存 streams 数据供后台线程使用
    global CACHED_STREAMS
    CACHED_STREAMS = npm_result['data']

    
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
        
        # 从数据库读取健康状态（而非内存）
        health = get_health_status(stream['id'])
        stream['health_status'] = health['status']
        stream['health_msg'] = health['msg']

    
    return jsonify({"success": True, "data": streams})


@app.route('/api/streams', methods=['POST'])
@login_required
def api_create_stream():
    """创建端口转发"""
    try:
        token = session.get('token')
        data = request.json

        print(f"📥 收到前端数据: {data}")

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
        incoming_port = int(incoming_port)
        forward_port = int(forward_port)
        if not (1 <= incoming_port <= 65535) or not (1 <= forward_port <= 65535):
            return jsonify({"success": False, "error": "端口号必须在 1-65535 之间"}), 400

        # 🔒 端口冲突验证：检查入站端口是否已被占用
        existing_streams = npm_get_streams(token)
        if existing_streams['success']:
            for stream in existing_streams['data']:
                if stream['incoming_port'] == incoming_port:
                    return jsonify({
                        "success": False, 
                        "error": f"入站端口 {incoming_port} 已被占用（ID: {stream['id']}），请使用其他端口"
                    }), 409  # 409 Conflict

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


@app.route('/api/streams/<int:stream_id>', methods=['PUT'])
@login_required
def api_update_stream(stream_id):
    """更新端口转发"""
    try:
        token = session.get('token')
        data = request.json

        print(f"📝 收到编辑请求: stream_id={stream_id}, data={data}")

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
        incoming_port = int(incoming_port)
        forward_port = int(forward_port)
        if not (1 <= incoming_port <= 65535) or not (1 <= forward_port <= 65535):
            return jsonify({"success": False, "error": "端口号必须在 1-65535 之间"}), 400

        # 🔒 端口冲突验证：检查入站端口是否被其他规则占用（排除自身）
        existing_streams = npm_get_streams(token)
        if existing_streams['success']:
            for stream in existing_streams['data']:
                if stream['incoming_port'] == incoming_port and stream['id'] != stream_id:
                    return jsonify({
                        "success": False,
                        "error": f"入站端口 {incoming_port} 已被其他规则占用（ID: {stream['id']}）"
                    }), 409

        # 调用 NPM 更新
        result = npm_update_stream(token, stream_id, incoming_port, forward_ip, forward_port)

        if result['success']:
            # 更新本地备注
            save_memo(stream_id, memo, doc_url, test_url, repo_url)
            return jsonify({"success": True, "message": "更新成功", "data": result['data']})
        else:
            return jsonify(result), 500

    except Exception as e:
        print(f"❌ 更新转发异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"服务器错误: {str(e)}"}), 500


@app.route('/api/streams/<int:stream_id>/toggle', methods=['PATCH'])
@login_required
def api_toggle_stream(stream_id):
    """切换端口转发启用/禁用状态"""
    try:
        token = session.get('token')
        data = request.json
        enabled = data.get('enabled', True)

        print(f"🔄 切换请求: stream_id={stream_id}, enabled={enabled}")

        result = npm_toggle_stream(token, stream_id, enabled)

        if result['success']:
            return jsonify({"success": True, "message": "状态切换成功", "data": result['data']})
        else:
            return jsonify(result), 500

    except Exception as e:
        print(f"❌ 切换状态异常: {str(e)}")
        return jsonify({"success": False, "error": f"服务器错误: {str(e)}"}), 500


# ==================== 主程序入口 ====================
if __name__ == '__main__':
    # 初始化数据库
    init_db()
    
    print("=" * 60)
    print("🚀 NPM Meta - Nginx Proxy Manager 增强管理工具")
    print(f"📍 访问地址: http://127.0.0.1:5001")
    print(f"🔗 NPM 服务器: {NPM_HOST}")
    print("=" * 60)
    
    # 启动后台健康检查线程
    t = threading.Thread(target=health_check_daemon, args=(app,), daemon=True)
    t.start()
    
    # 启动 Flask 应用
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=6789)


