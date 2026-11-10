from pathlib import Path

from agent.compiler import compile_urdf_report_maybe_timeout
from agent.feedback import render_compile_signals, compile_signal_bundle_from_exception


def main() -> None:
    try:
        report = compile_urdf_report_maybe_timeout(
            Path("model.py"), sdk_package="sdk", rewrite_visual_glb=False
        )
        print(render_compile_signals(report.signal_bundle))
    except Exception as exc:
        print(render_compile_signals(compile_signal_bundle_from_exception(exc)))


if __name__ == "__main__":
    main()
