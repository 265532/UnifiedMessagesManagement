"""应用入口。

启动：
    python app.py

然后打开 http://127.0.0.1:8000 ，用 demo / demo1234 登录。

接口分三组：
    /api/*        页面用的 JSON 接口
    /api/stream   SSE 实时推送
    /webhook/*    平台回调入口，接真平台时填到开放平台后台
"""

import json
import os
import queue
import secrets
import threading
import time
from functools import wraps

from flask import Flask, Response, jsonify, redirect, render_template, request, session

import config
from adapters.dingtalk_stream import get_runner as get_stream_runner
from core import bus, schema, service, state_machine, store


def create_app() -> Flask:
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    # 会话签名密钥。多实例部署时必须固定，否则各副本密钥不同，
    # 用户在负载均衡后端会反复被踢下线。
    app.secret_key = os.getenv("UMM_SECRET_KEY") or secrets.token_hex(16)
    app.permanent_session_lifetime = 60 * 60 * 8

    store.init_db()

    def _decorate(item: dict) -> None:
        """给列表项补上界面要用的显示字段，一次改齐，别在每个接口里各写一遍。"""
        item["summary"] = schema.summary(item)
        item["status_label"] = config.STATUS_LABEL.get(item["status"], item["status"])
        item["platform_label"] = config.PLATFORM_LABEL.get(item["platform"], item["platform"])
        item["platform_color"] = config.PLATFORM_COLOR.get(item["platform"], "#888")

    # ------------------------------------------------------------ 登录
    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user"):
                return jsonify({"error": "未登录或会话已失效", "code": "AUTH_REQUIRED"}), 401
            last = session.get("last_active", 0)
            if time.time() - last > config.SESSION_TIMEOUT_MINUTES * 60:
                session.clear()
                return jsonify({"error": "会话空闲超时，请重新登录", "code": "AUTH_TIMEOUT"}), 401
            session["last_active"] = time.time()
            return fn(*args, **kwargs)
        return wrapper

    @app.post("/api/login")
    def api_login():
        data = request.get_json(silent=True) or {}
        if data.get("username") == config.DEMO_USER and data.get("password") == config.DEMO_PASSWORD:
            session.permanent = True
            session["user"] = data["username"]
            session["last_active"] = time.time()
            return jsonify({"ok": True, "user": data["username"]})
        return jsonify({"ok": False, "error": "账号或密码不正确"}), 401

    @app.post("/api/logout")
    def api_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/demo")
    def demo_entry():
        """一键进入演示界面。

        只在 mock 模式下开放，接真平台后自动 403，避免成为绕过登录的口子。
        """
        if config.MODE != "mock":
            return "演示入口仅在模拟模式下开放", 403
        session.permanent = True
        session["user"] = config.DEMO_USER
        session["last_active"] = time.time()
        return redirect("/")

    # ------------------------------------------------------------ 页面
    @app.get("/")
    def index():
        """首屏数据由服务端直接渲染进去，打开就有内容，不需要等前端再拉一遍。"""
        boot = None
        if session.get("user"):
            items = store.list_messages(limit=60)
            for item in items:
                _decorate(item)

            detail = None
            if items:
                detail = {
                    "message": items[0],
                    "traces": store.get_traces(items[0]["id"]),
                    "status_label": config.STATUS_LABEL.get(items[0]["status"], items[0]["status"]),
                    "next_states": state_machine.next_states(items[0]["status"]),
                }

            boot = {"messages": items, "overview": service.state_snapshot(), "detail": detail}

        boot_json = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/") if boot else "null"
        return render_template("index.html", mode=config.MODE, boot_json=boot_json)

    # ------------------------------------------------------------ 数据接口
    @app.get("/api/overview")
    @login_required
    def api_overview():
        return jsonify(service.state_snapshot())

    @app.get("/api/messages")
    @login_required
    def api_messages():
        platform = request.args.get("platform") or None
        status = request.args.get("status") or None
        # 参数来自 URL，写错了不能让接口 500；也不允许一次拉全表
        try:
            limit = int(request.args.get("limit", 60))
        except (TypeError, ValueError):
            limit = 60
        limit = max(1, min(limit, 200))
        items = store.list_messages(platform=platform, status=status, limit=limit)
        for item in items:
            _decorate(item)
        return jsonify({"items": items, "count": len(items)})

    @app.get("/api/messages/<message_id>")
    @login_required
    def api_message_detail(message_id):
        message = store.get_message(message_id)
        if not message:
            return jsonify({"error": "消息不存在"}), 404
        return jsonify({
            "message": message,
            "traces": store.get_traces(message_id),
            "next_states": state_machine.next_states(message["status"]),
            "status_label": config.STATUS_LABEL.get(message["status"], message["status"]),
        })

    # ------------------------------------------------------------ 状态推进
    @app.post("/api/messages/<message_id>/display")
    @login_required
    def api_display(message_id):
        try:
            return jsonify({"ok": True, "message": service.display(message_id)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.post("/api/messages/<message_id>/process")
    @login_required
    def api_process(message_id):
        try:
            return jsonify({"ok": True, "message": service.process(message_id)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.post("/api/messages/<message_id>/reply")
    @login_required
    def api_reply(message_id):
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "回复内容不能为空"}), 400
        try:
            result = service.reply(message_id, text, simulate_failure=bool(data.get("simulate_failure")))
            return jsonify({"ok": result["result"] == "replied", **result})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.post("/api/messages/<message_id>/confirm")
    @login_required
    def api_confirm(message_id):
        try:
            return jsonify({"ok": True, "message": service.confirm(message_id)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    # ------------------------------------------------------------ 演示操作
    @app.post("/api/mock/push")
    @login_required
    def api_mock_push():
        data = request.get_json(silent=True) or {}
        result = service.receive_mock(data.get("platform"))
        return jsonify(result)

    @app.post("/api/mock/duplicate")
    @login_required
    def api_mock_duplicate():
        data = request.get_json(silent=True) or {}
        return jsonify(service.duplicate_demo(data.get("platform", "feishu")))

    @app.post("/api/mock/seed")
    @login_required
    def api_mock_seed():
        data = request.get_json(silent=True) or {}
        count = int(data.get("count", 5))
        return jsonify({"created": service.seed_demo(count)})

    @app.post("/api/reset")
    @login_required
    def api_reset():
        store.reset_demo_data()
        return jsonify({"ok": True})

    # ------------------------------------------------------------ SSE
    @app.get("/api/stream")
    @login_required
    def api_stream():
        def generate():
            q = bus.subscribe()
            try:
                yield "retry: 3000\n\n"
                while True:
                    try:
                        event = q.get(timeout=15)
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        yield ": keep-alive\n\n"
            finally:
                bus.unsubscribe(q)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # ------------------------------------------------------------ 平台回调
    @app.post("/webhook/<platform>")
    def webhook(platform):
        """真实平台把事件推到这里。飞书填回调地址、钉钉配机器人时用这个路径。"""
        payload = request.get_json(silent=True) or {}

        # 飞书保存回调地址时会先发一次 url_verification，必须原样回 challenge，
        # 否则开放平台后台一直提示「请求地址校验失败」，地址存不下来。
        if payload.get("type") == "url_verification":
            return jsonify({"challenge": payload.get("challenge", "")})

        try:
            result = service.receive(platform, payload, dict(request.headers))
        except service.ReceiveError as e:
            return jsonify({"code": -1, "msg": e.reason}), 400

        if result["result"] == "duplicate":
            return jsonify({"code": 0, "msg": "duplicate"})
        return jsonify({"code": 0, "msg": "ok"})

    @app.get("/healthz")
    def healthz():
        """健康检查，Docker 的 HEALTHCHECK 和部署演练都靠它。

        dingtalk_stream 这截用来确认长连接死没死：
        running=false 且 missing 有内容，说明开关开了但凭证或依赖没到位。
        """
        return jsonify({
            "status": "ok",
            "mode": config.MODE,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "dingtalk_stream": get_stream_runner().status(),
        })

    return app


def _mock_ticker() -> None:
    """开启自动推送时，按间隔往系统里灌模拟消息。"""
    while True:
        time.sleep(config.MOCK_INTERVAL_SECONDS)
        if config.MODE == "mock" and os.getenv("UMM_AUTO_PUSH", "0") == "1":
            try:
                service.receive_mock()
            except Exception:
                pass


if __name__ == "__main__":
    app = create_app()

    # 只在模拟模式灌演示数据。这里判的是「库空不空」，不是先清再灌：
    # 长连接收到的真实消息和 MODE 无关（模拟模式下也开着 Stream），
    # 以前无条件清库，一重启就把真人发来的消息连锅端了。
    # 需要干净的演示状态，网页上点「清空重来」，走 /api/reset。
    if config.MODE == "mock":
        if store.stats()["total"] == 0:
            service.seed_demo(6)
        else:
            print("库里已有数据，跳过演示数据注入；要干净演示态请点「清空重来」")
    else:
        print("真实模式启动，保留已有数据，不重置演示库")

    threading.Thread(target=_mock_ticker, daemon=True).start()

    # 钉钉长连接：开了开关就另起线程去连钉钉网关，真实消息从这条连接进系统。
    # 它跟 MODE 无关，真实模式、模拟模式都能同时开，方便一边演示一边接真消息。
    if config.DINGTALK_STREAM_ENABLED:
        get_stream_runner().start()

    print(f"统一消息管理入口已启动：http://{config.HOST}:{config.PORT}")
    print(f"运行模式：{config.MODE}   演示账号：{config.DEMO_USER} / {config.DEMO_PASSWORD}")
    app.run(host=config.HOST, port=config.PORT, threaded=True, debug=False)
