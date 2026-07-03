"""网页版：观鸟记录中心 → eBird 转换器（含热点匹配）"""
import streamlit as st
import pandas as pd
import io
import os
import sys

# 把 skill 脚本所在目录加入路径
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_THIS_DIR, 'scripts'))
from birdreport_to_ebird import province_convert
from hotspot_matcher import (
    fetch_hotspots,
    match_location,
    geocode_amap,
    PROVINCE_TO_ISO,
    _extract_cn,
)

st.set_page_config(
    page_title="观鸟记录中心 → eBird 转换器",
    page_icon="🦜",
    layout="centered"
)

st.title("🦜 观鸟记录中心 → eBird 转换器")
st.markdown("把中国观鸟记录中心（birdreport.cn）导出的 Excel 转换为 eBird 批量导入格式，**自动匹配 eBird 热点**。")

# ---- API Keys（通过 Streamlit Secrets 配置，见 .streamlit/secrets.toml） ----
ebird_key = st.secrets.get("EBIRD_API_KEY", "")
amap_key = st.secrets.get("AMAP_API_KEY", "")

if not ebird_key:
    st.error("未配置 eBird API Key，请在 Streamlit Cloud → Settings → Secrets 中设置。")
    st.stop()

if not amap_key:
    st.warning("未配置高德 API Key，无匹配热点时将无法做地理编码兜底。")

# ---- 缓存：拉取省份热点 ----
@st.cache_data(ttl=3600, show_spinner="正在加载 eBird 热点数据…")
def get_province_hotspots(province: str, key: str) -> list:
    return fetch_hotspots(province, key)


# ---- 使用说明 ----
with st.expander("📖 使用说明", expanded=False):
    st.markdown("""
    ### 步骤 1：从记录中心导出数据
    1. 打开 [birdreport.cn](http://birdreport.cn/) 网页版
    2. 进入「报告查询 → 定点记」
    3. 每页切成 200 条 → 全选 → 导出 Excel

    ### 步骤 2：上传 → 匹配热点 → 转换
    1. 上传 Excel 后，自动提取所有观测地点
    2. 点击「匹配热点」，自动匹配 eBird 热点（同名 / 子串 / 相似度）
    3. 未匹配的地点使用高德地图补充 GPS
    4. 检查匹配结果，必要时手动修正 → 点击转换 → 下载 CSV

    ### 步骤 3：上传到 eBird
    1. 打开 [ebird.org/import](https://ebird.org/import/status/all.htm)
    2. 上传 CSV，格式选「eBird 记录格式（扩展）」
    3. 「修复位置」步骤会根据 CSV 中的 GPS 自动定位，点击确认即可
    💡 eBird 语言选「中文（Sìm.）」，大部分鸟种可自动匹配
    """)


# ========== 核心转换函数 ==========

def convert_dataframe(
    df: pd.DataFrame,
    include_sw: bool,
    location_map: dict[str, dict] | None = None,
):
    """把 DataFrame 转成 eBird CSV。location_map 为 {地点名: {name, lat, lng}}。"""
    df.columns = [str(c).strip() for c in df.columns]
    try:
        iucn_pos = list(df.columns).index('IUCN受胁级别')
        loc_col_name = df.columns[iucn_pos - 1]
    except ValueError:
        raise ValueError("找不到 'IUCN受胁级别' 列，请确认这是从 birdreport.cn 导出的定点记数据")

    if location_map is None:
        location_map = {}

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
        raw_loc = str(row.get(loc_col_name, '')).strip()
        location_set.add(raw_loc)
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

        # 填入热点匹配信息
        loc_info = location_map.get(raw_loc, {})
        loc_name = loc_info.get('name', raw_loc)
        loc_lat = loc_info.get('lat', '')
        loc_lng = loc_info.get('lng', '')

        items = [''] * 19
        items[0] = common_name
        items[2] = sci_name
        items[3] = count
        items[4] = obs_note
        items[5] = loc_name          # Location Name
        items[6] = loc_lat            # Latitude
        items[7] = loc_lng            # Longitude
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


# ========== 热点匹配逻辑 ==========

def build_location_province_map(df: pd.DataFrame) -> dict[str, str]:
    """从 DataFrame 中提取 地点名 → 省份 映射（同一地点取首次出现的省份）。"""
    df.columns = [str(c).strip() for c in df.columns]
    iucn_pos = list(df.columns).index('IUCN受胁级别')
    loc_col = df.columns[iucn_pos - 1]
    mapping = {}
    for _, row in df.iterrows():
        loc = str(row.get(loc_col, '')).strip()
        if loc and loc not in mapping:
            mapping[loc] = str(row.get('省', '')).strip()
    return mapping


def auto_match_locations(
    locations: list[str],
    loc_province_map: dict[str, str],
    ebird_key: str,
    amap_key: str,
) -> dict[str, dict]:
    """自动匹配一批地点。返回 {原始地名: {name, lat, lng, source, candidates}}。"""
    # 收集所有涉及的省份
    provinces = set(loc_province_map.get(l, '') for l in locations)
    provinces.discard('')

    # 拉取所有相关省份的热点（缓存）
    all_hotspots = {}
    for prov in provinces:
        hotspots = get_province_hotspots(prov, ebird_key)
        if hotspots:
            all_hotspots[prov] = hotspots

    results = {}
    for loc in locations:
        prov = loc_province_map.get(loc, '')
        hotspots = all_hotspots.get(prov, [])

        # 尝试名字匹配
        matched = match_location(loc, hotspots)
        if matched:
            results[loc] = {
                'name': matched['locName'],
                'lat': matched.get('lat', ''),
                'lng': matched.get('lng', ''),
                'source': 'eBird 热点',
                'candidates': hotspots,  # 给用户手动选的候选
            }
            continue

        # 名字没匹配上 → 高德地理编码兜底
        if amap_key:
            lat, lng = geocode_amap(loc, prov, amap_key)
            if lat is not None:
                results[loc] = {
                    'name': loc,
                    'lat': lat,
                    'lng': lng,
                    'source': '高德坐标',
                    'candidates': hotspots,
                }
                continue

        # 完全兜底：无热点无坐标
        results[loc] = {
            'name': loc,
            'lat': '',
            'lng': '',
            'source': '无匹配',
            'candidates': hotspots,
        }

    return results


# ========== 主流程 ==========

st.subheader("1. 上传 Excel 文件")
uploaded = st.file_uploader(
    "选择从 birdreport.cn 导出的 Excel 文件",
    type=["xls", "xlsx"],
)

if uploaded is None:
    st.markdown("---")
    st.caption("开发者：司薇 | [GitHub](https://github.com/smilewsw/birding-ebird-converter)")
    st.stop()

# 读取数据
try:
    file_bytes = uploaded.read()
    df = pd.read_excel(io.BytesIO(file_bytes))
except Exception as e:
    st.error(f"读取 Excel 失败：{e}")
    st.stop()

# 提取列名
df.columns = [str(c).strip() for c in df.columns]
if 'IUCN受胁级别' not in df.columns:
    st.error("找不到 'IUCN受胁级别' 列，请确认这是从 birdreport.cn 导出的定点记数据。")
    st.stop()

# 提取地点→省份映射
loc_prov_map = build_location_province_map(df)
unique_locations = sorted(loc_prov_map.keys())

st.info(f"已读取 **{len(df)}** 条记录，共 **{len(unique_locations)}** 个不同地点，位于 **{len(set(loc_prov_map.values()))}** 个省份。")

# ===== 热点匹配 =====
st.subheader("2. 匹配 eBird 热点")
st.markdown("自动为每个地点匹配 eBird 热点。匹配不上的用高德补 GPS。你可以手动修正。")

if st.button("🔍 开始匹配热点", type="primary"):
    with st.spinner("正在拉取 eBird 热点并匹配…"):
        st.session_state["_loc_matches"] = auto_match_locations(
            unique_locations, loc_prov_map, ebird_key, amap_key
        )

# 展示匹配结果
if "_loc_matches" not in st.session_state:
    st.markdown("---")
    st.caption("开发者：司薇 | [GitHub](https://github.com/smilewsw/birding-ebird-converter)")
    st.stop()

matches = st.session_state["_loc_matches"]

# 统计
matched_hotspot = sum(1 for v in matches.values() if v['source'] == 'eBird 热点')
matched_amap = sum(1 for v in matches.values() if v['source'] == '高德坐标')
no_match = sum(1 for v in matches.values() if v['source'] == '无匹配')
col_a, col_b, col_c = st.columns(3)
col_a.metric("✅ 热点匹配", matched_hotspot)
col_b.metric("📍 GPS 兜底", matched_amap)
col_c.metric("❌ 无匹配", no_match)

# 可编辑表格：用户修正匹配
st.markdown("#### 匹配结果（可修改）")

edit_rows = []
for loc in unique_locations:
    m = matches[loc]
    # 构建候选下拉选项
    candidates = m.get('candidates', [])
    options = {}
    for h in candidates:
        label = f"[热点] {h['locName']} ({h.get('lat',''):.4f},{h.get('lng',''):.4f})" if isinstance(h, dict) else str(h)
        options[label] = h
    # 当前选择
    current_label = m['name']
    if m['source'] == 'eBird 热点' and m.get('lat'):
        current_label = f"[热点] {m['name']} ({m['lat']:.4f},{m['lng']:.4f})"
    edit_rows.append({
        "记录中心地点": loc,
        "省份": loc_prov_map.get(loc, ''),
        "匹配来源": m['source'],
        "当前匹配": current_label,
    })

edit_df = pd.DataFrame(edit_rows)
st.dataframe(edit_df, use_container_width=True, hide_index=True,
             column_config={
                 "记录中心地点": st.column_config.TextColumn(width="small"),
                 "省份": st.column_config.TextColumn(width="small"),
                 "匹配来源": st.column_config.TextColumn(width="small"),
                 "当前匹配": st.column_config.TextColumn(width="large"),
             })

# 用户手动覆盖：对每个无匹配/可疑匹配的地点，给出下拉选择
with st.expander("🔧 手动修正地点匹配（可选）"):
    for loc in unique_locations:
        m = matches[loc]
        candidates = m.get('candidates', [])
        if not candidates:
            st.caption(f"「{loc}」— 无候选热点")
            continue

        # 构建选项
        candidate_labels = [f"{_extract_cn(h['locName'])}  ({h.get('lat',''):.4f},{h.get('lng',''):.4f})" for h in candidates]

        # 当前值索引
        current_name = m['name']
        try:
            current_idx = next(i for i, h in enumerate(candidates) if h['locName'] == current_name)
        except StopIteration:
            current_idx = 0

        new_idx = st.selectbox(
            f"「{loc}」→",
            options=range(len(candidates)),
            format_func=lambda i: candidate_labels[i],
            index=min(current_idx, len(candidates) - 1),
            key=f"_sel_{loc}",
        )

        chosen = candidates[new_idx]
        matches[loc] = {
            'name': chosen['locName'],
            'lat': chosen.get('lat', ''),
            'lng': chosen.get('lng', ''),
            'source': 'eBird 热点（手动）',
            'candidates': candidates,
        }

# ===== 转换 =====
st.subheader("3. 转换并下载")

include_software_info = st.checkbox("在备注中包含软件信息", value=True)

if st.button("🚀 开始转换", type="primary", use_container_width=True):
    try:
        csv_bytes, summary, output_df = convert_dataframe(df, include_software_info, matches)

        st.success("✅ 转换成功！")
        c1, c2, c3 = st.columns(3)
        c1.metric("记录数", summary['records'])
        c2.metric("鸟种数", summary['species'])
        c3.metric("地点数", summary['locations'])
        c4, c5, c6 = st.columns(3)
        c4.metric("heard", summary['heard'])
        c5.metric("文件大小", f"{summary['size_kb']:.1f} KB")
        c6.metric("省份", summary['provinces'])

        if summary['size_kb'] > 1024:
            st.error("⚠️ 文件超过 1MB，eBird 不接受！请分批处理。")

        st.download_button(
            "⬇️ 下载 eBird CSV",
            data=csv_bytes,
            file_name=f"{os.path.splitext(uploaded.name)[0]}_ebird.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

        with st.expander("👀 预览前 5 行"):
            cols = ["俗名", "属", "拉丁名", "数量", "备注", "地点", "纬度", "经度",
                    "日期", "时间", "省份", "国家", "协议", "人数", "时长",
                    "完整", "距离", "面积", "提交备注"]
            preview = output_df.head().copy()
            preview.columns = cols
            st.dataframe(preview, use_container_width=True)

    except Exception as e:
        st.error(f"❌ 转换失败：{e}")
        st.exception(e)

st.markdown("---")
st.caption("开发者：司薇 | [GitHub](https://github.com/smilewsw/birding-ebird-converter) | 热点匹配由 eBird API + 高德地图提供")
