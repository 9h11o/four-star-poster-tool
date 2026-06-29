# 使用说明

## 网页版

启动：

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/web_app.py
```

打开：

```text
http://127.0.0.1:8765
```

网页里可以填写讲师信息、上传人像、实时预览，并点击“下载海报”。

项目经历需要换行时，直接在输入框里按回车；分号不会再自动换行。单行文字超过显示区域会被裁切，不会自动换到下一行。

普通背景 JPG / JPEG / PNG / WEBP 人像会自动尝试抠图；透明 PNG 会优先保留原透明通道。

## 网页批量生成

在网页下方的“批量生成”区域：

1. 上传讲师表格。
2. 可选上传多张人像。
3. 点击“批量生成并下载”。

表格字段：

```text
讲师姓名
项目经历
底部介绍
人像照片
```

人像匹配规则：

- 如果 `人像照片` 写的是 `assets/portraits/张三.png`，且该文件存在，会直接使用。
- 如果同时上传了多张人像，会按 `人像照片` 的文件名匹配，例如 `张三.png`。
- 如果在 Excel 对应讲师行里直接插入图片，且 `人像照片` 为空，会自动提取该行图片作为人像。
- 如果没有匹配到，会使用默认样例人像。

## 1. 修改讲师信息

优先修改这个 Excel：

```text
input/teachers.xlsx
```

也可以修改 CSV：

```text
input/sample_teachers.csv
```

字段说明：

```text
讲师姓名：讲师姓名
项目经历：项目经历，需要换行时在单元格里手动换行
底部介绍：底部介绍正文，服务过的品牌与介绍写在一起，自行换行区分即可
人像照片：人像图片路径或文件名
```

## 2. 放置人像

人像建议放在：

```text
assets/portraits/
```

然后在表格的 `portrait_path` 里填写类似：

```text
assets/portraits/李甲_transparent.png
```

## 3. 生成海报

在项目目录运行：

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/app.py --input input/teachers.xlsx
```

生成结果在：

```text
outputs/
```

## 4. 导出 JPG

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/app.py --input input/teachers.xlsx --format jpg
```

## 5. 重新生成 Excel 样例

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/app.py --make-sample-xlsx
```
