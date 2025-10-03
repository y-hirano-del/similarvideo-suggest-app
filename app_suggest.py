import streamlit as st
import pandas as pd
import os
import cv2
import imagehash
from PIL import Image
import numpy as np
from pydub import AudioSegment

# --- dejavuの設定 ---
from dejavu import Dejavu
from dejavu.recognize import FileRecognizer

# .streamlit/secrets.tomlからパスワードを読み込む
try:
    db_password = st.secrets["DB_PASSWORD"]
except:
    db_password = "your_mysql_password" # ローカルテスト用

config = {
    "database": {
        "host": "127.0.0.1",
        "user": "root",
        "password": db_password,
        "database": "dejavu",
    },
    "database_type": "mysql",
}

# グローバルスコープまたはキャッシュを利用してdjvオブジェクトを一度だけ初期化
@st.cache_resource
def get_dejavu():
    return Dejavu(config)

djv = get_dejavu()

# --- ヘルパー関数群 ---
def generate_visual_fingerprint(video_path, sample_rate=2):
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return None
        fingerprints = []
        fps = int(cap.get(cv.CAP_PROP_FPS))
        frame_interval = fps // sample_rate if fps > 0 else 15
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret: break
            if frame_count % frame_interval == 0:
                pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                phash = imagehash.phash(pil_img)
                fingerprints.append(str(phash))
            frame_count += 1
        cap.release()
        return "".join(fingerprints)
    except: return None

def calculate_visual_score(fp1, fp2):
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

def recognize_audio(video_path):
    try:
        audio = AudioSegment.from_file(video_path)
        temp_audio_path = "temp_audio_recognize.wav"
        audio.export(temp_audio_path, format="wav")
        
        recognizer = FileRecognizer(djv)
        result = recognizer.recognize_file(temp_audio_path)
        os.remove(temp_audio_path)
        
        return result.get('song_id', None)
    except Exception:
        return None

def main_app():
    """メインのアプリケーション部分を関数として定義"""
    st.title('🎬 映像・音声 類似動画検索アプリ')

    with st.sidebar:
        st.header("設定")
        db_file = st.file_uploader("1. fingerprint_av_tbl.xlsx をアップロード", type=['xlsx'])
        video_library_path = st.text_input("2. 動画ライブラリのフォルダパス", value="video_library")
        
        st.header("類似度スコアの重み付け")
        visual_weight = st.slider("映像スコアの重要度", 0, 100, 60, 5)
        audio_weight = 100 - visual_weight
        st.write(f"音声スコアの重要度: {audio_weight}%")

    if db_file:
        df = pd.read_excel(db_file, engine='openpyxl')
        st.success(f"データベースを読み込みました。({len(df)}件)")
        
        target_video = st.file_uploader("比較したい動画ファイルをアップロードしてください", type=['mp4', 'mov', 'webm', 'wmv'])

        if target_video:
            st.video(target_video)
            if st.button('類似動画を検索する', use_container_width=True, type="primary"):
                with st.spinner('映像と音声のフィンガープリントを計算・比較しています...'):
                    temp_video_path = f"./temp_{target_video.name}"
                    with open(temp_video_path, "wb") as f:
                        f.write(target_video.getbuffer())
                    
                    target_vfprint = generate_visual_fingerprint(temp_video_path)
                    target_afprint_id = recognize_audio(temp_video_path)

                    if target_vfprint:
                        results = []
                        for index, row in df.iterrows():
                            if row['filename'] == target_video.name:
                                continue
                            
                            v_score = calculate_visual_score(target_vfprint, row['fingerprint_visual'])
                            a_score = 100 if target_afprint_id and target_afprint_id == row['fingerprint_audio_id'] else 0
                            
                            final_score = (v_score * (visual_weight / 100)) + (a_score * (audio_weight / 100))
                            
                            results.append({
                                "filename": row['filename'],
                                "final_score": final_score,
                                "visual_score": v_score,
                                "audio_score": a_score
                            })
                        
                        st.session_state.results = sorted(results, key=lambda x: x['final_score'], reverse=True)
                    
                    os.remove(temp_video_path)

        if 'results' in st.session_state and st.session_state.results:
            st.header("🔍 検索結果：類似動画トップ3")
            for item in st.session_state.results[:3]:
                with st.expander(f"**{item['filename']}** (最終スコア: {item['final_score']:.2f})", expanded=True):
                    st.markdown(f"映像スコア: **{item['visual_score']:.2f}**, 音声スコア: **{item['audio_score']:.2f}**")
                    video_path = os.path.join(video_library_path, item['filename'])
                    if os.path.exists(video_path):
                        st.video(video_path)
                    else:
                        st.warning(f"動画ファイルが見つかりません: {video_path}")

# --- パスワード認証のロジック ---
try:
    password_guard = st.secrets["PASSWORD"]
except:
    password_guard = "test_password"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

st.sidebar.title("認証")
password_input = st.sidebar.text_input("パスワードを入力してください", type="password")
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