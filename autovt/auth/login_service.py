"""登录服务模块：对齐 Go 版本的加密登录协议，并提供本地账号密码缓存。"""

# 开启延迟注解，便于类型标注中使用前向引用。
from __future__ import annotations

# 导入 base64，用于编码/解码 AES-GCM 的密文和随机 nonce。
import base64
# 导入 json，用于组装请求体和解析响应体。
import json
# 导入 os，用于读取环境变量和生成随机字节。
import os
# 导入 sys，用于判断当前是否为打包运行形态。
import sys
# 导入 time，用于生成秒级时间戳。
import time
# 导入 dataclass，定义登录结果结构。
from dataclasses import dataclass
# 导入 Path，用于跨平台处理本地缓存文件路径。
from pathlib import Path
# 导入 Any，便于声明动态 JSON 数据类型。
from typing import Any
# 导入 urllib 异常类型，便于给出更清晰错误日志。
from urllib import error as urllib_error
# 导入 urllib 请求模块，避免新增 requests 依赖。
from urllib import request as urllib_request

# 导入 AESGCM，实现与 Go 端一致的 AES-GCM 加解密。
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 导入项目日志工厂，记录登录调用和异常信息。
from autovt.logs import get_logger
# 导入数据库路径解析方法，复用已有跨平台配置目录逻辑。
from autovt.userdb.user_db import resolve_user_db_path

# 定义与 Go 端一致的登录固定密钥（32 字节 AES-256）。
BIT_LOGIN_KEY = b"xUI7TjReIilQQKhqccFEPw6YsJA4PYeV"
# 定义与 Go 端一致的生产环境登录接口地址。
DEFAULT_PROD_API = "http://45.77.62.32:8989/bit_login"
# 定义与 Go 端一致的开发环境登录接口地址。
# DEFAULT_DEV_API = "http://127.0.0.1:8989/bit_login"
# 定义本地登录缓存文件名。
LOGIN_CACHE_FILENAME = "login_cache.json"


# 定义登录结果结构，统一返回“是否成功 + 文案 + token”。
@dataclass(slots=True)
class LoginResult:
    # 声明登录是否成功。
    ok: bool
    # 声明给 UI 展示的结果文案。
    msg: str
    # 声明登录成功后返回的 token（调试跳过时也会给占位 token）。
    token: str = ""


# 定义登录服务类，负责 API 登录、缓存读取和缓存写入。
class LoginService:
    # 定义初始化方法。
    def __init__(self) -> None:
        # 创建登录模块日志对象。
        self.log = get_logger("auth.login")
        # 保存本地缓存文件名。
        self.cache_filename = LOGIN_CACHE_FILENAME
        # 在启动阶段校验密钥长度，避免运行时才发现协议不兼容。
        if len(BIT_LOGIN_KEY) != 32:
            # 抛出明确错误，提示配置异常。
            raise ValueError("BIT_LOGIN_KEY 长度必须是 32 字节")

    # 定义“是否启用调试跳过登录”判断方法。
    def is_skip_api_login(self) -> bool:
        # 读取环境变量并清理空白字符。
        env_value = str(os.getenv("GITXUZAN_LOGIN", "")).strip()
        # 仅当值为 "1" 时启用跳过模式。
        return env_value == "1"

    # 定义解析登录 API 地址的方法（与 Go 逻辑一致）。
    def resolve_login_api(self) -> str:
        # 优先读取 BITLOGIN_API 环境变量。
        env_api = str(os.getenv("BITLOGIN_API", "")).strip()
        # 环境变量有值时直接使用。
        if env_api != "":
            # 返回覆盖后的 API 地址。
            return env_api
        # 读取 AUTOVT_LOGIN_ENV（Python 侧补充）环境变量。
        login_env = str(os.getenv("AUTOVT_LOGIN_ENV", "")).strip().lower()
        # 显式指定 dev 时强制走开发地址。
        if login_env in {"dev", "development"}:
            # 返回开发环境 API。
            return DEFAULT_PROD_API
        # 显式指定 prod 时强制走生产地址。
        if login_env in {"prod", "production"}:
            # 返回生产环境 API。
            return DEFAULT_PROD_API


        # 判断当前是否为打包运行（PyInstaller/Frozen）形态。
        is_frozen_runtime = bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None))
        # 源码运行（含 uv run）默认走开发环境地址，方便本地调试。
        if not is_frozen_runtime:
            # 返回开发环境 API。
            return DEFAULT_PROD_API
        # 默认走生产环境 API。
        return DEFAULT_PROD_API

    # 定义生成随机 nonce 字符串的方法（base64 输出）。
    def _new_nonce(self, size: int = 16) -> str:
        # 生成指定长度的随机字节数组。
        raw_bytes = os.urandom(size)
        # 使用标准 base64 编码输出文本。
        return base64.b64encode(raw_bytes).decode("utf-8")

    # 定义 AES-GCM 加密方法，返回 payload 和 nonce（均为 base64）。
    def _encrypt_payload(self, data: dict[str, Any]) -> tuple[str, str]:
        # 把请求对象序列化成紧凑 JSON 字节串。
        plain_bytes = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        # 生成 12 字节随机 nonce（与 Go 版一致）。
        nonce_bytes = os.urandom(12)
        # 创建 AES-GCM 加密器。
        aes_gcm = AESGCM(BIT_LOGIN_KEY)
        # 执行加密得到“密文 + tag”。
        cipher_bytes = aes_gcm.encrypt(nonce_bytes, plain_bytes, None)
        # 把密文编码为 base64 文本。
        payload_b64 = base64.b64encode(cipher_bytes).decode("utf-8")
        # 把 nonce 编码为 base64 文本。
        nonce_b64 = base64.b64encode(nonce_bytes).decode("utf-8")
        # 返回请求 payload 和 nonce。
        return payload_b64, nonce_b64

    # 定义 AES-GCM 解密方法，返回响应明文字典。
    def _decrypt_payload(self, payload_b64: str, nonce_b64: str) -> dict[str, Any]:
        # 把 base64 密文解码成字节串。
        cipher_bytes = base64.b64decode(payload_b64)
        # 把 base64 nonce 解码成字节串。
        nonce_bytes = base64.b64decode(nonce_b64)
        # 创建 AES-GCM 解密器。
        aes_gcm = AESGCM(BIT_LOGIN_KEY)
        # 解密得到响应明文 JSON 字节串。
        plain_bytes = aes_gcm.decrypt(nonce_bytes, cipher_bytes, None)
        # 解析 JSON 并返回字典对象。
        return dict(json.loads(plain_bytes.decode("utf-8")))

    # 定义“定位登录缓存文件路径”的方法。
    def _resolve_login_cache_path(self) -> Path:
        # 复用 user_db 的跨平台配置目录解析，并获取目录路径。
        base_dir = resolve_user_db_path().parent
        # 拼出登录缓存文件完整路径。
        return base_dir / self.cache_filename

    # 定义读取本地缓存账号密码的方法。
    def load_saved_credentials(self) -> tuple[str, str]:
        # 先解析缓存路径。
        cache_path = self._resolve_login_cache_path()
        # 缓存文件不存在时返回空账号和空密码。
        if not cache_path.exists():
            # 返回空字符串对。
            return "", ""
        # 使用异常保护读取流程，避免缓存损坏导致界面崩溃。
        try:
            # 读取 UTF-8 文本内容。
            raw_text = cache_path.read_text(encoding="utf-8")
            # 解析 JSON 数据。
            cache_obj = dict(json.loads(raw_text))
            # 读取账号并清理空白字符。
            account = str(cache_obj.get("account", "")).strip()
            # 读取密码（密码不做 strip，避免误删合法前后空格）。
            password = str(cache_obj.get("password", ""))
            # 返回缓存账号和密码。
            return account, password
        # 缓存读取失败时记录异常并回退空值。
        except Exception as exc:
            # 记录异常堆栈，便于排查缓存格式错误。
            self.log.exception("读取登录缓存失败", cache_path=str(cache_path), error=str(exc))
            # 回退空账号和空密码。
            return "", ""

    # 定义保存本地账号密码缓存的方法。
    def save_credentials(self, account: str, password: str) -> None:
        # 解析缓存文件路径。
        cache_path = self._resolve_login_cache_path()
        # 把账号做 trim，减少无意义空白字符干扰。
        safe_account = str(account).strip()
        # 密码保持原样保存，避免改动用户真实输入。
        safe_password = str(password)
        # 组装缓存对象。
        cache_obj = {
            # 保存账号字段。
            "account": safe_account,
            # 保存密码字段。
            "password": safe_password,
            # 保存更新时间戳，方便问题排查。
            "update_at": int(time.time()),
        }
        # 使用异常保护写文件流程，避免文件系统问题中断登录。
        try:
            # 确保缓存目录存在。
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            # 按 UTF-8 写入 JSON 缓存文件。
            cache_path.write_text(json.dumps(cache_obj, ensure_ascii=False, indent=2), encoding="utf-8")
            # 记录缓存保存成功日志。
            self.log.info("登录缓存已保存", cache_path=str(cache_path), account=safe_account)
        # 写入失败时记录异常，不向上抛出。
        except Exception as exc:
            # 记录失败堆栈，便于定位权限或磁盘问题。
            self.log.exception("保存登录缓存失败", cache_path=str(cache_path), error=str(exc))

    # 定义发起一次加密登录请求的方法，成功返回 token。
    def _do_encrypted_login(self, account: str, password: str) -> str:
        # 解析最终登录接口地址。
        api_url = self.resolve_login_api()
        # 组装与 Go 端一致的登录明文对象。
        req_obj = {
            # 账号字段会做 trim，保持与 Go 逻辑一致。
            "account": str(account).strip(),
            # 密码字段保持原始输入。
            "password": str(password),
            # 使用 UTC 秒级时间戳防重放。
            "ts": int(time.time()),
            # 使用 16 字节随机 nonce（base64）防重放。
            "nonce": self._new_nonce(16),
        }
        # 执行 AES-GCM 加密得到 payload/nonce。
        payload_b64, nonce_b64 = self._encrypt_payload(req_obj)
        # 组装 POST 请求 JSON 包体。
        body_bytes = json.dumps({"nonce": nonce_b64, "payload": payload_b64}, ensure_ascii=False).encode("utf-8")
        # 构造 HTTP POST 请求对象。
        req = urllib_request.Request(
            # 传入登录接口地址。
            url=api_url,
            # 传入请求体字节串。
            data=body_bytes,
            # 设置请求头为 JSON。
            headers={"Content-Type": "application/json"},
            # 明确使用 POST 方法。
            method="POST",
        )
        # 发起请求并设置 10 秒超时（与 Go 逻辑一致）。
        with urllib_request.urlopen(req, timeout=10) as resp:
            # 读取 HTTP 状态码。
            status_code = int(resp.getcode())
            # 非 200 直接按登录失败处理。
            if status_code != 200:
                # 抛出可读错误，供上层统一记录。
                raise RuntimeError(f"login failed, status_code={status_code}")
            # 读取响应原始字节。
            resp_bytes = resp.read()
        # 把响应字节转成字符串。
        resp_text = resp_bytes.decode("utf-8", errors="replace")
        # 解析响应 JSON 包体。
        env_obj = dict(json.loads(resp_text))
        # 提取响应 nonce 字段。
        resp_nonce = str(env_obj.get("nonce", "")).strip()
        # 提取响应 payload 字段。
        resp_payload = str(env_obj.get("payload", "")).strip()
        # 响应字段缺失时直接报错。
        if resp_nonce == "" or resp_payload == "":
            # 抛出明确错误，便于定位服务端协议异常。
            raise RuntimeError("login response missing nonce or payload")
        # 解密响应得到明文对象。
        plain_obj = self._decrypt_payload(payload_b64=resp_payload, nonce_b64=resp_nonce)
        # 读取 token 字段。
        token = str(plain_obj.get("token", "")).strip()
        # 返回 token 给调用方判断是否登录成功。
        return token

    # 定义公开登录方法，供登录页直接调用。
    def login(self, account: str, password: str) -> LoginResult:
        # 标准化账号文本。
        safe_account = str(account).strip()
        # 标准化密码文本。
        safe_password = str(password)
        # 当开启调试跳过模式时直接返回成功。
        if self.is_skip_api_login():
            # 记录跳过模式日志。
            self.log.warning("检测到 GITXUZAN_LOGIN=1，跳过 API 登录", account=safe_account)
            # 返回成功结果。
            return LoginResult(ok=True, msg="登录成功", token="debug-skip")
        # 正常模式下调用 API 执行加密登录。
        try:
            # 请求服务端并提取 token。
            token = self._do_encrypted_login(account=safe_account, password=safe_password)
            # token 为空按失败处理。
            if token == "":
                # 返回统一失败文案（对齐 Go 端）。
                return LoginResult(ok=False, msg="登录失败", token="")
            # 记录登录成功日志。
            self.log.info("登录成功", account=safe_account, api=self.resolve_login_api())
            # 返回成功结果（对齐 Go 端文案）。
            return LoginResult(ok=True, msg="登录成功", token=token)
        # 捕获 HTTP 错误并分类处理（401 属于预期失败，不打印堆栈）。
        except urllib_error.HTTPError as exc:
            # 401 未授权时按账号密码错误处理，避免误判为程序崩溃。
            if int(getattr(exc, "code", 0)) == 401:
                # 记录告警日志（无堆栈）。
                self.log.warning(
                    "登录失败：账号或密码错误",
                    account=safe_account,
                    api=self.resolve_login_api(),
                    http_code=exc.code,
                )
                # 返回可读失败文案给登录页。
                return LoginResult(ok=False, msg="账号或密码错误", token="")
            # 其他 HTTP 状态码按登录失败处理，记录错误日志（无堆栈）。
            self.log.error(
                "登录请求 HTTP 异常",
                account=safe_account,
                api=self.resolve_login_api(),
                http_code=int(getattr(exc, "code", 0)),
                error=str(exc),
            )
            # 返回失败结果。
            return LoginResult(ok=False, msg="登录失败", token="")
        # 捕获网络异常并记录日志（无堆栈）。
        except urllib_error.URLError as exc:
            # 记录网络层异常日志。
            self.log.error("登录请求网络异常", account=safe_account, api=self.resolve_login_api(), error=str(exc))
            # 返回失败结果。
            return LoginResult(ok=False, msg="登录失败", token="")
        # 捕获其他异常并记录日志。
        except Exception as exc:
            # 记录通用异常堆栈。
            self.log.exception("登录请求失败", account=safe_account, api=self.resolve_login_api(), error=str(exc))
            # 返回失败结果。
            return LoginResult(ok=False, msg="登录失败", token="")
