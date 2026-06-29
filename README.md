# 讲师海报生成工具

本项目用于开发「懂车学四星讲师」海报自动生成工具。

## 怎么使用

先进入项目目录：

```bash
cd /Users/tiaotiaohu/Desktop/Workspace/Project_01_讲师海报生成工具
```

启动网页版：

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/web_app.py
```

打开：

```text
http://127.0.0.1:8765
```

飞书机器人入口与云端部署说明见：

```text
docs/feishu_deploy.md
```

云端部署后，机器人菜单里填写：

```text
https://你的云端域名/feishu/start
```

不要填写本地地址 `http://127.0.0.1:8765`。

生成样例海报：

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/app.py
```

生成结果会放在：

```text
outputs/
```

## 填写讲师信息

你可以直接修改：

```text
input/sample_teachers.csv
```

也可以先生成 Excel 样例：

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/app.py --make-sample-xlsx
```

然后修改：

```text
input/teachers.xlsx
```

Excel / CSV 字段：

```text
讲师姓名
项目经历
底部介绍
人像照片
```

说明：

- `讲师姓名`：讲师姓名。
- `项目经历`：项目经历，需要换行时在单元格里手动换行。
- `底部介绍`：底部个人介绍，服务过的品牌与介绍写在一起，自行换行区分即可，超过 6 行会截断。
- `人像照片`：人像图片路径或文件名，建议放在 `assets/portraits/`；也可以在网页批量区域单独上传多张人像。

## 批量生成

使用 CSV：

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/app.py --input input/sample_teachers.csv
```

使用 Excel：

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/app.py --input input/teachers.xlsx
```

指定输出格式：

```bash
/Users/tiaotiaohu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/app.py --input input/teachers.xlsx --format jpg
```

## 当前支持

- 四星讲师模板。
- 网页实时预览与下载。
- 网页批量导入表格并下载压缩包。
- 单个或批量生成。
- CSV / Excel 导入。
- PNG / JPG 导出。
- 固定前景层、人像、姓名材质字、项目经历、底部介绍框自动合成。
- 普通背景 JPG / JPEG / PNG / WEBP 人像会自动尝试抠图。
- 底部区域按 `Gap1 = Gap2 = Gap3` 动态布局。

## 项目规则

本项目必须同时遵循：

1. Workspace 全局规则：`/Users/tiaotiaohu/Desktop/Workspace/AGENTS.md`
2. 项目开发守则：`AGENT.md`

所有项目相关文件、素材、代码、文档和导出结果，都必须保存在本项目文件夹内，不能散落到桌面、下载目录或其他位置。

## 目录说明

- `assets/`：模板底图、分层素材、字体、人像样例、输入样例等。
- `docs/`：PRD、方案、验收记录、排版说明等。
- `input/`：讲师信息表格。
- `outputs/`：最终生成的海报、截图、导出结果等。
- `src/`：代码、配置、脚本等。
