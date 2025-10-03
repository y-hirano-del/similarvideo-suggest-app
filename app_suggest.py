import streamlit as st
import pandas as pd
import os
import cv2
import imagehash
from PIL import Image
import numpy as np

# --- ヘルパー関数群 ---

def generate_visual_fingerprint(video_path, sample_rate=2):
    """映像指紋(pHash)を生成する"""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            st.error(f"エラー: 動画ファイル '{video_path}' を開けませんでした。")
            return None
        fingerprints = []
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        frame_interval = fps // sample_rate if fps > 0 else 15
        frame_count = 0
        progress_bar = st.progress(0, text="フィンガープリントを計算中...")
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        while True:
            ret, frame = cap.read()
            if not ret: break
            if frame_count % frame_interval == 0:
                pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                phash = imagehash.phash(pil_img)
                fingerprints.append(str(phash))
            frame_count += 1
            if total_frames > 0:
                progress_bar.progress(frame_count / total_frames)
        
        progress_bar.empty()
        cap.release()
        return "".join(fingerprints)
    except Exception as e:
        st.error(f"エラー: フィンガープリント生成中にエラー: {e}")
        return None

def calculate_visual_score(fp1, fp2):
    """映像の類似度スコア(0-100)を返す"""
    if not fp1 or not fp2: return 0
    hash_size = 16
    hashes1 = [imagehash.hex_to_hash(str(fp1[i:i+hash_size])) for i in range(0, len(str(fp1)), hash_size)]
    hashes2 = [imagehash.hex_to_hash(str(fp2[i:i+hash_size])) for i in range(0, len(str(fp2)), hash_size)]
    if not hashes1 or not hashes2: return 0
    if len(hashes1) > len(hashes2): base_hashes, search_hashes = hashes2, hashes1
    else: base_hashes, search_hashes = hashes1, hashes2
    total_distance = sum(min(bh - sh for sh in search_hashes) for bh in base_hashes)
    average_distance = total_distance / len(base_hashes)
    max_dist = 32
    score = max(0, 100 - (average_distance / max_dist) * 100)
    return score

def main_app():
    """メインのアプリケーション部分"""
    st.title('🎬 類似動画検索アプリ (映像のみ)')

    with st.sidebar:
        st.header("設定")
        db_file = st.file_uploader("1. fingerprint_tbl.xlsx をアップロード", type=['xlsx'])
        video_library_path = st.text_input("2. 動画ライブラリのフォルダパス", value="video_library")

    if db_file:
        df = pd.read_excel(db_file, engine='openpyxl')
        st.success(f"データベースを読み込みました。({len(df)}件)")
        
        target_video = st.file_uploader("比較したい動画ファイルをアップロード", type=['mp4', 'mov', 'webm', 'wmv'])

        if target_video:
            st.video(target_video)
            if st.button('類似動画を検索する', use_container_width=True, type="primary"):
                with st.spinner('フィンガープリントを計算・比較しています...'):
                    temp_video_path = f"./temp_{target_video.name}"
                    with open(temp_video_path, "wb") as f: f.write(target_video.getbuffer())
                    
                    target_fp = generate_visual_fingerprint(temp_video_path)
                    
                    if target_fp:
                        results = []
                        for index, row in df.iterrows():
                            if row['filename'] == target_video.name: continue
                            score = calculate_visual_score(target_fp, row['fingerprint'])
                            results.append({"filename": row['filename'], "score": score})
                        
                        st.session_state.results = sorted(results, key=lambda x: x['score'], reverse=True)
                    
                    os.remove(temp_video_path)

        if 'results' in st.session_state and st.session_state.results:
            st.header("🔍 検索結果：類似動画トップ3")
            for item in st.session_state.results[:3]:
                with st.expander(f"**{item['filename']}** (スコア: {item['score']:.2f})", expanded=True):
                    video_path = os.path.join(video_library_path, item['filename'])
                    if os.path.exists(video_path):
                        st.video(video_path)
                    else:
                        st.warning(f"動画ファイルが見つかりません: {video_path}")

# --- パスワード認証のロジック ---
# (この部分は変更なし)
try:
    password_guard = st.secrets["PASSWORD"]
except:
    password_guard = "test_password"

if "logged_in" not in st.session_state: st.session_state.logged_in = False

st.sidebar.title("認証")
password_input = st.sidebar.text_input("パスワードを入力", type="password")
login_button = st.sidebar.button("ログイン")

if login_button and password_input == password_guard:
    st.session_state.logged_in = True
    st.sidebar.success("ログインしました。")
elif login_button:
    st.sidebar.error("パスワードが違います。")

if st.session_state.logged_in:
    main_app()
else:
    st.warning("サイドバーからログインしてください。")