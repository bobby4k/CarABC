from carabc.cli import main
from carabc.exceptions import ValidationError


if __name__ == "__main__":
    try:
        main()
    except ValidationError as exc:
        raise SystemExit(f"错误: {exc}")
