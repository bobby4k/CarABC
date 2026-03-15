# CarABC
为 4-7 岁、喜欢汽车的小男孩打造的每日一课，融合汽车知识点的拼音 + 英语启蒙。

### 项目目标
- 为喜欢汽车的小朋友生成 100 天学习卡片。
- 每天输出一张 A5 卡片，每张 A4 纸排版两天内容，方便家用打印和裁切。
- 每日固定包含：一张主题图片、一句带重点拼音标注的中文句子、一句带重点释义的英文句子、一个互动小任务。
- OpenCode 负责主题策划与结构化内容产出，Python 脚本负责图片生成、日志记录和 PDF 合成。

### 项目思路
- 先用 `output/themes.yaml` 作为唯一结构化数据源，统一管理主题、风格、图片提示词、中英文句子和互动任务。
- 再由 `generate_pdf.py` 读取 `config.yaml` 和 `output/themes.yaml`，按天生成图片并合成 PDF。
- 主题规划遵循阶段递进，同时尽量前置经典车型、经典工程车和孩子更感兴趣的实车主题。
- 图片生成采用“规则/安全优先卡通、品牌/车型优先写实”的策略，兼顾认知启蒙与视觉吸引力。

### 适合人群
- 4-7 岁、喜欢汽车的小男孩及亲子家庭。
- 想把汽车兴趣和识字、拼音、英语启蒙结合起来的家长。
- 希望用 A4 打印后裁切成学习卡片的家庭、小型课堂或亲子活动场景。

### 优点
- 内容结构固定，便于批量生成、审校和打印。
- 主题可以覆盖汽车认知、规则安全、工程车、经典车型、品牌等多个方向。
- 结构化 YAML 数据源清晰，后续扩展脚本、排版和重跑都更方便。
- 支持分段生成和 `--force` 强制重建，适合逐步迭代内容与版式。

### 局限与注意点
- 当前主题数据还在逐步补齐，未补满 `rules.total_days` 时需要配合 `--days` 使用。
- 图片生成依赖外部模型平台和 API Key，网络或接口失败时需要重试。
- 版式目前优先兼顾家用打印和实现稳定性，后续仍可继续美化。
- 中文句子与阶段字库的严格匹配仍需要持续校对和优化。

### 安装依赖
- 采用 Python 虚拟环境
```bash
sudo apt-get update
grep -v '^#' apt.txt | xargs sudo apt-get install -y
python -m venv pycarabc
source pycarabc/bin/activate
pip install -r requirements.txt
```

### 进入虚拟环境
- 如果你使用仓库内虚拟环境：
```bash
source pycarabc/bin/activate
```
- 如果你使用统一路径的虚拟环境：
```bash
source /opt/pyenvs/pycarabc/bin/activate
```

### 运行命令
- 生成当前已准备好的全部天数：
```bash
python generate_pdf.py
```
- 只生成指定天数范围的图片和 PDF：
```bash
python generate_pdf.py --days 1-20
```
- 只生成单天或离散天数：
```bash
python generate_pdf.py --days 5
python generate_pdf.py --days 1,3,5-8
```
- 强制覆盖已存在图片并重新生成：
```bash
python generate_pdf.py --days 1-20 --force
```

### 当前输入输出
- 配置文件：`config.yaml`
- 主题数据：`output/themes.yaml`
- 图片输出目录：`cards/dayXXX/image.jpg`
- PDF 输出文件：`output/car_learning.pdf`
- 生成日志：`output/generated_log.log`

### 日志说明
- 日志为逐行文本格式，每行一条记录，便于排查与重跑。
- 日志字段包括：时间、天数、主题、阶段、图片路径、图片状态、是否进入 PDF、错误信息。
- 常见状态：
  - `generated`：新生成图片
  - `regenerated`：强制覆盖后重新生成
  - `skipped_existing`：图片已存在，跳过生成
  - `failed`：图片生成失败，但流程继续

### 使用注意事项
- 当前 `output/themes.yaml` 若未补满 `rules.total_days`，请使用 `--days` 指定已准备好的范围。
- 若图片 API Key 未配置，可先手动放入测试图片，再生成 PDF 检查版式。
- 中文字体路径来自 `config.yaml` 的 `font_path`，若字体缺失，PDF 可能回退到系统字体。
- 图片生成失败不会中断全部流程，PDF 可继续输出留白或占位。
