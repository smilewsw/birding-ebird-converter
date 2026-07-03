# 观鸟记录中心 → eBird 转换器

把中国观鸟记录中心（birdreport.cn）导出的一次性上传到 eBird，自动匹配 eBird 热点。

在线使用：**[birding-ebird-converter.streamlit.app](https://birding-ebird-converter.streamlit.app)**

## 功能

- 上传记录中心 Excel（定点记）→ 一键导出 eBird CSV
- **自动匹配 eBird 热点**（同名 / 子串 / 相似度）
- 匹配不上时高德地图地理编码补充 GPS 坐标
- 支持手动修正匹配结果
- 所有处理在本地浏览器完成，数据不上传服务器

## 使用方法

1. 打开 [网页](https://birding-ebird-converter.streamlit.app)
2. 从鸟记录中心导出 Excel（「报告查询 → 定点记」→ 全选 → 导出）
3. 上传 → 点击「匹配热点」→ 确认匹配结果
4. 点击「开始转换」→ 下载 CSV
5. 去 [ebird.org/import](https://ebird.org/import) 上传（格式选「eBird 记录格式（扩展）」）

## 技术栈

- Streamlit · Pandas · openpyxl
- eBird API 2.0（热点匹配）
- 高德地图 API（地理编码兜底）

## 本地运行

```bash
pip install -r requirements.txt
streamlit run web_app.py
```

需要在 `.streamlit/secrets.toml` 中配置 API Key：

```toml
EBIRD_API_KEY = "your_ebird_api_key"
AMAP_API_KEY = "your_amap_api_key"
```

## 开发者

司薇 | [GitHub](https://github.com/smilewsw/birding-ebird-converter)

感谢 [birdreportcn-to-ebird](https://github.com/sun-jiao/birdreportcn-to-ebird) 提供数据转换基础逻辑。
