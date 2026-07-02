"""网页版：观鸟记录中心 → eBird 转换工具"""
import streamlit as st
import pandas as pd
import io
import os
import sys

# 把 skill 脚本所在目录加入路径
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_THIS_DIR, 'scripts'))
from birdreport_to_ebird import province_convert

st.set_page_config(
    page_title="观鸟记录中心 → eBird 转换器",
    page_icon="🦜",
    layout="centered"
)

st.title("🦜 观鸟记录中心 → eBird 转换器")
st.markdown("把中国观鸟记录中心（birdreport.cn）导出的 Excel 转换为 eBird 批量导入格式。")

# ===== 使用说明 =====
with st.expander("📖 使用说明（首次使用必读）", expanded=False):
    st.markdown("""
    ### 步骤 1：从记录中心导出数据
    1. 打开 [birdreport.cn](http://birdreport.cn/) 网页版
    2. 进入「报告查询 → 定点记」
    3. 每页显示数量切到 200 条
    4. 全选记录 → 导出 Excel

    ### 步骤 2：上传并转换
    1. 把 Excel 文件拖到下面
    2. 点击「开始转换」
    3. 转换完成后下载 CSV

    ### 步骤 3：上传到 eBird
    1. 打开 [ebird.org/import](https://ebird.org/import/status/all.htm)
    2. 上传下载的 CSV
    3. 格式选「eBird 记录格式（扩展）」
    4. 按提示手动修正物种和地点
    """)

# ===== 文件上传 =====
st.subheader("1. 上传 Excel 文件")
uploaded = st.file_uploader(
    "选择从 birdreport.cn 导出的 Excel 文件",
    type=["xls", "xlsx"],
    help="文件应包含列：报告编号、观测开始时间、观测结束时间、中文名、拉丁名、省、鸟种数量、IUCN受胁级别"
)

# ===== 转换选项 =====
st.subheader("2. 转换选项")
include_software_info = st.checkbox(
    "在备注中包含软件信息",
    value=True,
    help="勾选后，eBird 备注里会写 'Originally uploaded to birdreport.cn...'"
)


def convert_dataframe(df: pd.DataFrame, include_sw: bool):
    """把读取的 DataFrame 转成 eBird CSV 字节流 + 摘要信息"""
    df.columns = [str(c).strip() for c in df.columns]
    try:
        iucn_pos = list(df.columns).index('IUCN受胁级别')
        loc_col_name = df.columns[iucn_pos - 1]
    except ValueError:
        raise ValueError("找不到 'IUCN受胁级别' 列，请确认这是从 birdreport.cn 导出的定点记数据")

    ebird_data = []
    special_map = {"鹗": "鹗 (鱼鹰)", "隼": "隼形目未知"}
    heard_count = 0
    species_set = set()
    location_set = set()
    province_set = set()

    for _, row in df.iterrows():
        common_name = str(row.get('中文名', '')).strip()
        if common_name in special_map:
            common_name = special_map[common_name]
        if len(common_name) < 2:
            common_name += " "
        sci_name = str(row.get('拉丁名', '')).strip()
        count_val = row.get('鸟种数量', 1)
        count = int(count_val) if pd.notnull(count_val) and count_val > 0 else 1
        obs_note = "heard" if (pd.notnull(count_val) and count_val == 0) else ""
        if obs_note == "heard":
            heard_count += 1
        species_set.add(common_name)
        location_set.add(str(row.get(loc_col_name, '')).strip())
        province_set.add(str(row.get('省', '')).strip())

        start_dt = pd.to_datetime(row['观测开始时间'])
        end_dt = pd.to_datetime(row['观测结束时间'])
        duration = int((end_dt - start_dt).total_seconds() / 60)
        duration_remark = ""
        if duration > 1440 or duration < 0:
            duration_remark = f" [Time Error: {duration}min]"
            duration = 1440
        elif duration < 1:
            duration = 1

        report_id = str(row.get('报告编号', 'Unknown'))
        if include_sw:
            remarks = f"Originally uploaded to birdreport.cn, record id = {report_id}.{duration_remark}"
        else:
            remarks = f"birdreport.cn record id = {report_id}.{duration_remark}"

        items = [''] * 19
        items[0] = common_name
        items[2] = sci_name
        items[3] = count
        items[4] = obs_note
        items[5] = str(row.get(loc_col_name, '')).strip()
        items[8] = start_dt.strftime('%m/%d/%Y')
        items[9] = start_dt.strftime('%H:%M')
        items[10] = province_convert(row['省'])
        items[11] = 'CN'
        items[12] = 'stationary'
        items[13] = '1'
        items[14] = duration
        items[15] = 'Y'
        items[18] = remarks
        ebird_data.append(items)

    output_df = pd.DataFrame(ebird_data)
    csv_buf = io.StringIO()
    output_df.to_csv(csv_buf, index=False, header=False, encoding='utf-8-sig')
    csv_bytes = csv_buf.getvalue().encode('utf-8-sig')

    return csv_bytes, {
        'records': len(ebird_data),
        'species': len(species_set),
        'locations': len(location_set),
        'provinces': len(province_set),
        'heard': heard_count,
        'size_kb': len(csv_bytes) / 1024,
    }, output_df


# ===== 转换按钮 =====
if uploaded is not None:
    st.subheader("3. 转换结果")
    if st.button("🚀 开始转换", type="primary", use_container_width=True):
        try:
            file_bytes = uploaded.read()
            df = pd.read_excel(io.BytesIO(file_bytes))
            csv_bytes, summary, output_df = convert_dataframe(df, include_software_info)

            st.success("✅ 转换成功！")
            col1, col2, col3 = st.columns(3)
            col1.metric("记录数", summary['records'])
            col2.metric("鸟种数", summary['species'])
            col3.metric("地点数", summary['locations'])
            col4, col5, col6 = st.columns(3)
            col4.metric("heard 数量", summary['heard'])
            col5.metric("文件大小", f"{summary['size_kb']:.1f} KB")
            col6.metric("省份", summary['provinces'])
            if summary['size_kb'] > 1024:
                st.error("⚠️ 文件超过 1MB，eBird 不接受！请分批处理。")
            st.markdown("---")
            st.download_button(
                "⬇️ 下载 eBird CSV",
                data=csv_bytes,
                file_name=f"{os.path.splitext(uploaded.name)[0]}_ebird.csv",
                mime="text/csv",
                type="primary",
                use_container_width=True
            )
            with st.expander("👀 预览前 5 行"):
                st.dataframe(output_df.head(), use_container_width=True)
        except Exception as e:
            st.error(f"❌ 转换失败：{e}")
            st.exception(e)

st.markdown("---")
st.caption("基于开源项目 [birdreportcn-to-ebird](https://github.com/sun-jiao/birdreportcn-to-ebird) 改编")
