# 导入 sys 模块，用于动态追加项目根目录到导入路径。
import sys
# 导入 time 模块，用于生成测试邮箱时间戳。
import time
# 导入 Path，用于计算项目根目录。
from pathlib import Path

# 获取当前测试文件绝对路径。
CURRENT_FILE = Path(__file__).resolve()
# 计算项目根目录（tests 的上一层）。
PROJECT_ROOT = CURRENT_FILE.parent.parent
# 如果项目根目录不在 Python 搜索路径里。
if str(PROJECT_ROOT) not in sys.path:
    # 把项目根目录加入搜索路径，确保可导入 autovt 包。
    sys.path.insert(0, str(PROJECT_ROOT))

# 导入数据库封装类，作为本次调试入口。
from autovt.userdb import UserDB
# 导入用户记录结构，方便写入测试数据。
from autovt.userdb import UserRecord
# 导入路径解析函数，方便打印默认数据库路径。
from autovt.userdb import resolve_user_db_path


# 定义一个最简单的调试方法，手动运行即可。
def test_userdb_smoke() -> None:
    # 打印调试开始日志。
    print("[debug] 开始调试 UserDB")
    # 解析默认 user.db 路径。
    default_path = resolve_user_db_path()
    # 打印默认路径，确认是否符合预期。
    print(f"[debug] 默认数据库路径: {default_path}")
    # 创建数据库对象（默认使用解析后的 user.db 路径）。
    db = UserDB()
    # 打印对象中的数据库路径。
    print(f"[debug] 实际使用路径: {db.path}")
    # 建立数据库连接并自动建表。
    db.connect()
    # 打印连接成功日志。
    print("[debug] 数据库连接成功，t_user 表已确保存在")
    # 生成一条不会重复的调试邮箱，避免污染固定测试账号。
    email = f"debug_{int(time.time())}@example.com"
    # 组装一条测试记录（补齐新增必填 client_id，并带上 device 展示字段示例）。
    record = UserRecord(
        # 设置邮箱账号（唯一键）。
        email_account=email,
        # 设置邮箱密码。
        email_pwd="22323",
        # 设置邮箱授权码。
        email_access_key="debug_access_key",
        # 设置微软 OAuth 应用 client_id。
        client_id="9e5f94bc-e8a4-4e73-b8be-63364c29d753",
        # 设置姓字段。
        first_name="Toms",
        # 设置名字段。
        last_name="Lee",
        # 设置 vinted 密码（必填）。
        pwd="vt_debug_pwd",
        # 设置账号状态。
        status=1,
        # 设置 fb 注册状态。
        fb_status=1,
        # 设置设备 ID（仅展示字段）。
        device="emulator-5554",
        # 设置备注。
        msg="debug run",
    # 测试记录构造完成。
    )
    # 写入测试记录（同邮箱重复执行会走更新）。
    db.upsert_user(record)
    # 打印写入完成日志。
    print(f"[debug] 已写入测试数据: {email}")
    # 按邮箱查询刚写入的数据。
    row = db.get_user_by_email(email)
    # 打印查询结果，便于你调试观察。
    print(f"[debug] 查询结果: {row}")
    # 按状态查询最多 3 条记录做演示。
    rows = db.list_users_by_status(1, limit=3)
    # 打印批量查询结果。
    print(f"[debug] status=1 前 3 条: {rows}")
    # 读取默认配置项用于调试验证。
    conf = db.get_config("mojiwang_run_num")
    # 打印配置查询结果。
    print(f"[debug] 配置 mojiwang_run_num: {conf}")
    # 关闭数据库连接。
    db.close()
    # 打印调试结束日志。
    print("[debug] 调试结束")


# 当脚本被直接运行时进入这里。
if __name__ == "__main__":
    # 直接调用最简单调试方法。
    test_userdb_smoke()
