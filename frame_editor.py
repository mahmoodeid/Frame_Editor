# frame_editor_streamlit.py
# Streamlit-based web portal version of the Skeleton Frame Editor with ReID.

import streamlit as st
import pandas as pd
import zipfile
import io
import math
from PIL import Image

# Remove decimals helper (same as original)
def remove_decimals(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if col.endswith(("_X", "_Y", "_Z")):
            df[col] = df[col].round().astype("Int64")
    return df

st.set_page_config(page_title="Skeleton Frame Editor Web", layout="wide")
st.title("🖥️ Skeleton Frame Editor (Web)")

# Uploads
csv_file = st.file_uploader("Upload raw_skeletons.csv", type="csv")
zip_file = st.file_uploader("Upload frames.zip (folder of frame_XXXXXX.png)", type="zip")
names_text = st.text_area("Enter person names (one per line)")

if csv_file and zip_file and names_text:
    # Read names
    person_names = [n.strip() for n in names_text.splitlines() if n.strip()]
    if not person_names:
        st.error("Please enter at least one person name.")
        st.stop()

    # Load CSV
    df = pd.read_csv(csv_file)
    df = remove_decimals(df)

    # Load images into memory mapping frame_idx -> bytes
    zip_bytes = io.BytesIO(zip_file.read())
    zf = zipfile.ZipFile(zip_bytes)
    img_map = {}
    for fname in zf.namelist():
        base = fname.split('/')[-1]
        if base.startswith("frame_") and base.lower().endswith(('.png','.jpg','.jpeg')):
            idx = int(base.replace('frame_','').split('.')[0])
            img_map[idx] = zf.read(fname)

    # Prepare session state
    if 'frame_pos' not in st.session_state:
        st.session_state.frame_pos = 0
        st.session_state.id_to_name = {}
        st.session_state.name_to_neck = {}
        st.session_state.uninterested = set()

    frames = sorted(df['Frame'].unique())
    total = len(frames)

    # Sidebar: frame navigation
    st.sidebar.header("Navigation")
    st.sidebar.slider("Frame Index", 0, total-1, key='frame_pos', format="%d/%d" % (st.session_state.frame_pos+1, total))

    # Current frame
    frame_idx = frames[st.session_state.frame_pos]
    st.subheader(f"Frame {frame_idx} ({st.session_state.frame_pos+1}/{total})")

    # Display image
    if frame_idx in img_map:
        img = Image.open(io.BytesIO(img_map[frame_idx]))
        st.image(img, use_column_width=True)
    else:
        st.warning("Image not found for this frame.")

    # Filter rows for this frame
    sub = df[df['Frame'] == frame_idx].copy()
    sub['_neck'] = list(zip(sub['NECK_X'], sub['NECK_Y'], sub['NECK_Z']))
    
    # Assign previous mappings
    used = set()
    for i, row in sub.iterrows():
        bid = row['BodyID']
        if bid in st.session_state.id_to_name:
            sub.at[i, 'PersonName'] = st.session_state.id_to_name[bid]
            used.add(sub.at[i, 'PersonName'])
        else:
            sub.at[i, 'PersonName'] = ""

    # Suggest for unmapped
    for i, row in sub.iterrows():
        if not row['PersonName'] and row['BodyID'] not in st.session_state.uninterested:
            neck = row['_neck']
            best, bdist = None, None
            for name, prev_neck in st.session_state.name_to_neck.items():
                if name in used: continue
                d = math.dist(neck, prev_neck)
                if best is None or d < bdist:
                    best, bdist = name, d
            if best:
                sub.at[i, 'PersonName'] = best
                st.session_state.id_to_name[row['BodyID']] = best
                st.session_state.name_to_neck[best] = neck
                used.add(best)

    # Editable table
    sub_edit = sub[['Frame','Timestamp','BodyID','PersonName']]
    edited = st.experimental_data_editor(
        sub_edit,
        num_rows="fixed",
        column_config={
            'PersonName': st.column_config.SelectboxColumn(
                'PersonName', options=[""] + person_names
            )
        },
        hide_index=True
    )

    # Save selections
    for i, row in edited.iterrows():
        bid = row['BodyID']
        name = row['PersonName']
        if name:
            st.session_state.id_to_name[bid] = name
            neck = sub.loc[sub['BodyID']==bid, '_neck'].iloc[0]
            st.session_state.name_to_neck[name] = neck
            st.session_state.uninterested.discard(bid)
        else:
            st.session_state.id_to_name.pop(bid, None)
            st.session_state.uninterested.add(bid)

    # Controls
    col1, col2, col3 = st.columns(3)
    if col1.button("◀ Prev") and st.session_state.frame_pos > 0:
        st.session_state.frame_pos -= 1
    if col2.button("Next ▶") and st.session_state.frame_pos < total-1:
        st.session_state.frame_pos += 1
    if col3.button("Export Edited CSV"):
        # build full output
        out_rows = []
        for f in frames:
            block = df[df['Frame']==f]
            for _, r in block.iterrows():
                bid = r['BodyID']
                name = st.session_state.id_to_name.get(bid, "")
                if name:
                    row = r.to_dict()
                    row['PersonName'] = name
                    out_rows.append(row)
        out_df = pd.DataFrame(out_rows)[df.columns.tolist() + ['PersonName']]
        csv_bytes = out_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Edited CSV", csv_bytes, "edited_skeletons.csv", mime="text/csv")
