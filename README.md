# 观鸟记录中心 → eBird 转换器

把中国观鸟记录中心（birdreport.cn）导出的 Excel 转换为 eBird 批量导入格式。

## 使用方法

1. 打开网页
2. 上传 Excel 文件
3. 点击「开始转换」
4. 下载生成的 CSV
5. 去 https://ebird.org/import 上传

## 技术栈

- Streamlit (Web UI)
- Pandas (Excel 解析)
- 改编自 [birdreportcn-to-ebird](https://github.com/sun-jiao/birdreportcn-to-ebird)
