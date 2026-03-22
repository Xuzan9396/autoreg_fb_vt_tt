# 导入 Path，用于定位项目根目录。
from pathlib import Path
# 导入 sys，用于在直跑脚本时补充模块搜索路径。
import sys


# 先尝试正常包导入（推荐运行方式）。
try:
    # 导入 Vinted 验证码主入口方法。
    from autovt.emails import getvinted_code
# 直跑文件时包路径可能不可见，这里做一次路径兜底。
except ModuleNotFoundError:
    # 计算项目根目录路径（当前文件在 autovt/emails/test_vt.py，下两级是项目根）。
    project_root = Path(__file__).resolve().parents[2]
    # 把项目根目录插入 sys.path 首位，保证 `import autovt` 可用。
    sys.path.insert(0, str(project_root))
    # 补路径后再次导入目标方法。
    from autovt.emails import getvinted_code

# uv run python -m autovt.emails.test_vt
# uv run python autovt/emails/test_vt.py

# 定义主函数，便于 `python -m autovt.emails.test_vt` 与直跑两种方式复用。
def main() -> None:
    # 调用验证码获取入口并接收结果。
    ok, result = getvinted_code(
        # 传入微软 OAuth client_id。
        client_id="9e5f94bc-e8a4-4e73-b8be-63364c29d753",
        # 传入目标邮箱账号。
        email_name="StaceyGreenfeldersntgu@outlook.com",
        # 传入 refresh_token 用于刷新 access_token。
        refresh_token="M.C513_SN1.0.U.-CgrokmZGmk*eRyA34uTGVZlHbzdhNRnKZiRmuH9F*13UgF3iy*5iD2!p5sNdfWAdTT0ESa!362nWvqS33PoX2Lfxw6O7Bm4DfED2VmMIki9K2GPNTK3HZGOF2hlDddlX69OhlUPIq3sLhc6ktexoIA5VDf1vTzN688HHSeYsvtI6OpS*3uGSxowEG0CDYFOXxZL89s!c3!Ha*K2INzpe4XDbpos8SxIXJOxoE52ojReTaeImq4TrSG7gbNQz!981GIEa9B*7twnNdyBJhXtzIfIRTDq8uJb6g4umxBFGAW2QsfDKxX6CFgsgIT4FuLX9hryjPZkeVX3*y8vGikQAQSiNc8J4OB*pM227ZNhChNWMWLMYeOD82zkipLMg3d11uCEdcJYNhdTyuhFVkxFIjQPREorUv5U6e4TKDwK4MX7ofyV!ZT6pAem0oKpgY*Nqwg$$",
        # 关闭调试落盘（需要调试时改为 True）。
        is_debug=False,
    )
    # 打印结果状态与内容，便于终端直接查看。
    print("ok=", ok, "result=", result)


# 作为脚本直接执行时进入主函数。
if __name__ == "__main__":
    # 执行主流程。
    main()
