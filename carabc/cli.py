from __future__ import annotations

import argparse
from pathlib import Path

from .config_loader import load_yaml
from .exceptions import ValidationError
from .images.manager import process_image
from .logging_utils import load_model_state, write_log
from .pdf import print_summary, render_pdf
from .utils import parse_days_expr
from .validators import validate_themes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成汽车学习卡片图片与 PDF")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--days", help="生成指定天数，支持 5、1-20、1,3,5-8 形式")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存在的图片")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    config = load_yaml(root / args.config)
    selected_days = parse_days_expr(args.days, config["rules"]["total_days"])
    themes = load_yaml(root / config["paths"]["themes_file"])
    items = validate_themes(themes, config, selected_days, root)
    state_file = root / config["paths"]["model_state_file"]
    try:
        model_state = load_model_state(state_file, config.get("image_models", []))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    results = [process_image(item, config, root, args.force, model_state, state_file) for item in items]
    write_log(root / config["paths"]["log_file"], results)
    pdf_file = render_pdf(items, config, root, selected_days)
    print_summary(items, results, pdf_file)
