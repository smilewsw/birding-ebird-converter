# 观鸟记录中心 → eBird 转换器

把中国观鸟记录中心（birdreport.cn）导出的记录一键转换为 eBird CSV，自动匹配 eBird 热点。

在线使用：**[birding-ebird-converter.streamlit.app](https://birding-ebird-converter.streamlit.app)**

## 功能

### 定点记转换
- 按地点名匹配 eBird 热点（同名 / 子串 / 相似度四级模糊匹配）
- 未匹配的地点使用高德地图地理编码补充 GPS 坐标
- 支持手动修正匹配结果（选择框可输入关键字模糊查询热点）

### 随手记转换
- 按 GPS 坐标匹配 5km 内最近的 eBird 热点（本地 Haversine 距离计算，速度快）
- 未匹配热点的坐标使用高德逆地理编码获取真实 POI 名称（如「通州大运河森林公园」）
- 全省热点一次性拉取，仅对未匹配的坐标调高德 API，避免不必要的网络请求

### 通用
- 自动识别记录类型（有「观测结束时间」= 定点记，无 = 随手记）
- 匹配结果一目了然：✅ 热点匹配 / 📍 高德地点 / 📌 原始坐标 / ✏️ 手动修改
- 手动修正区域对未匹配热点的条目标记 ⚠️ 提醒，方便快速定位
- 所有处理在浏览器端完成，数据不上传服务器

## 使用方法

1. 打开 [网页](https://birding-ebird-converter.streamlit.app)
2. 从鸟记录中心导出 Excel（定点记或随手记，每页 200 条 → 全选 → 导出）
3. 上传 Excel → 点击「匹配热点」→ 检查结果（可手动修正）
4. 点击「开始转换」→ 下载 CSV
5. 去 [ebird.org/import](https://ebird.org/import) 上传（格式选「eBird 记录格式（扩展）」）

> 💡 eBird 语言选「中文（Sìm.）」，大部分鸟种可自动匹配

## 技术栈

- Streamlit · Pandas · openpyxl
- eBird API 2.0（热点匹配：全省热点拉取 + 本地 Haversine 距离计算）
- 高德地图 API（地理编码 / 逆地理编码兜底）
- ThreadPoolExecutor（并发请求高德 API）

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
