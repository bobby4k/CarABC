为 4-7 岁、喜欢汽车的小男孩及亲子家庭，制作的100天小课程，融合汽车知识点的拼音 + 英语启蒙。

### 项目目标
- 为喜欢汽车的小朋友以及 想把汽车兴趣和识字、拼音、英语启蒙结合起来的家长, 生成 100 天学习卡片。
- 每天输出一张 A5 卡片，每张 A4 纸排版两天内容，方便家用打印和裁切。
    - 内容结构固定，便于批量生成、审校和打印。
- 每日固定包含：一张主题图片、一句带重点拼音标注的中文句子、一句带重点释义的英文句子、一个互动小任务。
    - 主题可以覆盖汽车认知、规则安全、工程车、经典车型、品牌等多个方向。
- OpenCode 负责主题策划与结构化内容产出，Python 脚本负责图片生成、日志记录和 PDF 合成。
    - 图片生成采用“规则/安全优先卡通、品牌/车型优先写实”的策略，兼顾认知启蒙与视觉吸引力。



### 优缺点及注意事项
- 结构化 YAML 数据源清晰，后续扩展脚本、排版和重跑都更方便。
- 支持分段生成和 `--force` 强制重建，适合逐步迭代内容与版式。
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
- PDF 输出文件：`output/car_learning_dayX-Y.pdf`
- 生成日志：`output/generated_log.log`
- 模型额度状态：`output/model_usage_state.json`

### 日志说明
- 日志为逐行文本格式，每行一条记录，便于排查与重跑。
- 日志字段包括：时间、天数、主题、阶段、图片路径、图片状态、使用模型、尝试链路、额度变化、是否进入 PDF、错误信息。
- 常见状态：
  - `generated`：新生成图片
  - `regenerated`：强制覆盖后重新生成
  - `skipped_existing`：图片已存在，跳过生成
  - `failed`：图片生成失败，但流程继续

### 多模型回退与额度文件
- 图片模型按 `config.yaml` 中的顺序依次尝试，当前默认顺序是：`qwen-image-2.0 -> qwen-image-plus -> wanx-v1`。
- 若某个模型调用成功，则立即使用该模型结果，不再继续尝试后续模型。
- 若某个模型调用失败，则自动切换到下一个模型。
- 若某个模型剩余额度为 `0`，会直接跳过并继续尝试下一个模型。
- 模型额度状态保存在 `output/model_usage_state.json`。
- 如果 `output/model_usage_state.json` 不存在，则表示不做额度限制，模型可持续调用。
- 当额度文件存在时，只有“成功生成图片”才会将对应模型的剩余额度减 `1`；失败不会扣减。

### 兼容其他图片平台
- 当前图片 provider 已按模块拆分在 `carabc/images/providers.py`。
- 除了现有阿里百炼 provider，还提供了一个 `OpenAICompatibleImagesProvider` 模板，便于后续接入其他兼容 OpenAI Images API 的平台。
- 这类平台通常只需要在 `config.yaml` 中新增模型配置，并把 `api_mode` 设为 `openai_images`。
- 典型配置示例：
```yaml
image_models:
  - name: demo-openai-images
    provider: custom
    api_mode: openai_images
    model_name: gpt-image-1
    api_key_env: OPENAI_API_KEY
    base_url: https://api.openai.com/v1
    size: 1024x1024
    n: 1
    timeout_seconds: 180
```

### 额度文件示例
```json
{
  "qwen-image-2.0": 90,
  "qwen-image-plus": 90,
  "wanx-v1": 500
}
```

### 运行示例
- 强制重建第 1-2 天：
```bash
python generate_pdf.py --days 1-2 --force
```
- 输出 PDF 文件名会自动带上天数后缀，例如：
  - `output/car_learning_day1-2.pdf`
  - `output/car_learning_day3-4.pdf`
  - `output/car_learning_day5.pdf`

### 使用注意事项
- 当前 `output/themes.yaml` 若未补满 `rules.total_days`，请使用 `--days` 指定已准备好的范围。
- 若图片 API Key 未配置，可先手动放入测试图片，再生成 PDF 检查版式。
- 中文字体路径来自 `config.yaml` 的 `font_path`，若字体缺失，PDF 可能回退到系统字体。
- 图片生成失败不会中断全部流程，PDF 可继续输出留白或占位。
- 若你想测试模型切换，可手动修改 `output/model_usage_state.json` 中的额度为 `0`。
