# 导入 Path，用于定位项目根目录。
from pathlib import Path
# 导入 sys，用于在直跑脚本时补充模块搜索路径。
import sys


# 先尝试正常包导入（推荐运行方式）。
try:
    # 导入 Facebook 验证码主入口方法。
    from autovt.emails import getfackbook_code
# 直跑文件时包路径可能不可见，这里做一次路径兜底。
except ModuleNotFoundError:
    # 计算项目根目录路径（当前文件在 autovt/emails/test.py，下两级是项目根）。
    project_root = Path(__file__).resolve().parents[2]
    # 把项目根目录插入 sys.path 首位，保证 `import autovt` 可用。
    sys.path.insert(0, str(project_root))
    # 补路径后再次导入目标方法。
    from autovt.emails import getfackbook_code

# uv run python -m autovt.emails.test
# uv run python autovt/emails/test.py

# 定义主函数，便于 `python -m autovt.emails.test` 与直跑两种方式复用。
def main() -> None:
    # 调用验证码获取入口并接收结果。
    ok, result = getfackbook_code(
        # 传入微软 OAuth client_id。
        client_id="9e5f94bc-e8a4-4e73-b8be-63364c29d753",
        # 传入目标邮箱账号。
        email_name="JessicaSoto1074@hotmail.com",
        # 传入 refresh_token 用于刷新 access_token。
        refresh_token="M.C536_SN1.0.U.-Ctymy8c3zLXovA*7TQbg0df3w9uPpXS7ieT9qR3D0CViNMMcnd*JMxUFcpsQ93uo13urlTOMY8BRtqJ37aot8M1sPYm1SHvNyyZDrb7leQKfTpNYvlU8ik0phSM7sOsl6i2Or2LJf4*04haMb2!01N*t2v03WEJ2KofyBG11SIMCMRz1l1OoiaPQzVzlZfO1P0CcuQ8ao71nT8LeuQRAT0TSSx86ZGeUDYTB4YhWxr04mskVCDJhav!cGmT99Msis16siOiemkkZqS1hqxSxzo5zKpUBd93T6oi4VUbJs2OwCtMJqwpKrPzz9xl2pMlcv*ReObBR6CyQfNKPwr74hNs45KxIoqHn*vDrB6f8ZY4F6VVGfbLLenrDMQpWX1mEr285viIueTZTjLkeryD8AAVu0DsEA0tK9cXt9lWhbmbyZgEMOie!sHCfOgLOWAhv8A$$",
        # 关闭调试落盘（需要调试时改为 True）。
        is_debug=False,
    )
    # 打印结果状态与内容，便于终端直接查看。
    print("ok=", ok, "result=", result)


# 作为脚本直接执行时进入主函数。
if __name__ == "__main__":
    # 执行主流程。
    main()
