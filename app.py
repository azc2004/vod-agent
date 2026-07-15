import streamlit as st
import os
import requests
from video_generator import generate_product_video

st.set_page_config(page_title="상품 동영상 생성 봇", page_icon="🎬", layout="wide")

@st.dialog("🎥 생성 완료된 동영상 재생", width="small")
def play_video_modal(video_path):
    st.write("로컬 파일로부터 생성된 동영상을 로드했습니다.")
    import base64
    try:
        with open(video_path, "rb") as vf:
            b64 = base64.b64encode(vf.read()).decode()
        st.markdown(
            f'<div style="width: 100%; aspect-ratio: 9/16; overflow: hidden; border-radius: 12px; border: 1px solid #ddd; background-color: #000; margin-bottom: 12px;">'
            f'  <video autoplay loop controls playsinline style="width: 100%; height: 100%; object-fit: cover;">'
            f'    <source src="data:video/webm;base64,{b64}" type="video/webm">'
            f'  </video>'
            f'</div>',
            unsafe_allow_html=True
        )
    except Exception as e:
        st.video(video_path, autoplay=True)

st.title("🎬 상품 동영상 자동 생성기")
st.markdown("""
하프클럽 상품 리스트에서 상품을 선택하거나 상품 번호를 직접 입력하여 
**모델 컷, 다각도 뷰, 상세 재질 컷**이 포함된 홍보용 영상을 자동으로 생성합니다.
""")

# API를 통해 상품 리스트 가져오기
@st.cache_data(ttl=600)
def fetch_product_list(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        hits = data.get("data", {}).get("result", {}).get("hits", {}).get("hits", [])
        products = []
        for hit in hits:
            source = hit.get("_source", {})
            prd_no = source.get("prdNo")
            prd_nm = source.get("prdNm")
            prd_img = source.get("prdImgUrl") or source.get("prdImg")
            if prd_img and not prd_img.startswith("http"):
                prd_img = "https://cdn2.halfclub.com/" + prd_img
            brand = source.get("brandNm") or source.get("selAcntNm")
            price = source.get("dcPrcPc") or source.get("selPrc")
            if prd_no and prd_nm:
                products.append({
                    "id": str(prd_no),
                    "name": prd_nm,
                    "img": prd_img,
                    "brand": brand,
                    "price": price
                })
        return products
    except Exception as e:
        st.error(f"상품 리스트 로드 오류: {e}")
        return []

# 비디오 생성 모델 기본값 설정
video_model = "Google Veo 3.1 Lite"

def test_gemini_key(api_key):
    try:
        from google import genai as google_genai_sdk
        client = google_genai_sdk.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Hello, please reply with 'API Key is working!'"
        )
        if response.text:
            return True, f"✅ 성공! 응답: {response.text.strip()}"
        return False, "응답 텍스트가 비어 있습니다."
    except Exception as e:
        return False, str(e)

# 사이드바 API 설정 UI
st.sidebar.header("🔑 API 설정 및 테스트")

# secrets.toml에서 API Key 기본값 로드
default_gemini_key = ""
default_openai_key = ""
try:
    if "GEMINI_API_KEY" in st.secrets:
        default_gemini_key = st.secrets["GEMINI_API_KEY"]
    if "OPENAI_API_KEY" in st.secrets:
        default_openai_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    pass

selected_api_key = st.sidebar.text_input(
    "Gemini API Key",
    value=default_gemini_key,
    type="password",
    help="Google AI Studio에서 발급받은 Gemini API Key를 입력하세요."
)

openai_api_key = st.sidebar.text_input(
    "OpenAI API Key (선택)",
    value=default_openai_key,
    type="password",
    help="이미지 필터링 및 스마트 크롭(GPT-4o-mini)에 사용될 OpenAI API Key입니다."
)

if st.sidebar.button("Gemini Key 테스트", use_container_width=True):
    if not selected_api_key:
        st.sidebar.warning("먼저 Gemini API Key를 입력해주세요.")
    else:
        with st.sidebar.spinner("Gemini API 연결 확인 중..."):
            success, msg = test_gemini_key(selected_api_key.strip())
            if success:
                st.sidebar.success(msg)
            else:
                st.sidebar.error(f"연결 실패: {msg}")

# 상품 목록 불러오기
default_url = "https://hapix.halfclub.com/searches/prdList/?selAcntCd=A6082&limit=0,40&sortSeq=12&siteCd=1&device=pc&icnSet="
products = fetch_product_list(default_url)

# 로컬에 생성된 동영상 파일들에서 상품 번호(prdNo) 추출
created_prd_ids = []
if os.path.exists("output_videos"):
    for filename in os.listdir("output_videos"):
        if filename.startswith("result_") and filename.endswith(".webm"):
            prd_id = filename[7:-5]
            if prd_id:
                created_prd_ids.append(prd_id)

# 현재 리스트에 포함되어 있지 않은 생성된 상품 번호 선별
existing_prd_ids = {prd["id"] for prd in products} if products else set()
missing_prd_ids = [pid for pid in created_prd_ids if pid not in existing_prd_ids]

# 누락된 생성 상품이 있다면 검색 API를 통해 추가 조회 및 병합
if missing_prd_ids and products is not None:
    missing_url = f"https://hapix.halfclub.com/searches/prdList/?prd_no={','.join(missing_prd_ids)}&device=pc&limit=0,100&sortSeq=12"
    extra_products = fetch_product_list(missing_url)
    if extra_products:
        seen_ids = set(existing_prd_ids)
        for prd in extra_products:
            if prd["id"] not in seen_ids:
                products.append(prd)
                seen_ids.add(prd["id"])

# 영상이 생성된 상품 우선 정렬 (안정 정렬 적용)
if products:
    products = sorted(
        products,
        key=lambda prd: not os.path.exists(f"output_videos/result_{prd['id']}.webm")
    )

# 레이아웃 나누기 (왼쪽: 상품 리스트, 오른쪽: 동영상 생성 및 결과)
col1, col2 = st.columns([2, 1])

# 우측 동영상 생성 영역(col2)을 스크롤 시 고정(Sticky)하기 위한 CSS 주입
st.markdown("""
    <style>
    [data-testid="stHorizontalBlock"] > div:nth-child(2) {
        position: -webkit-sticky;
        position: sticky;
        top: 2rem;
        align-self: start;
        height: auto;
    }
    </style>
""", unsafe_allow_html=True)

selected_prd_id = None

with col1:
    st.subheader("🛍️ 상품 리스트 (최근 40개)")
    if products:
        # 그리드 레이아웃으로 상품 리스트 뿌려주기
        cols = st.columns(4)
        for idx, prd in enumerate(products):
            with cols[idx % 4]:
                with st.container(border=True):
                    # 이미 생성된 동영상이 있는지 확인
                    video_file_path = f"output_videos/result_{prd['id']}.webm"
                    video_exists = os.path.exists(video_file_path)
                    
                    # 재생 상태 관리 키
                    playing_key = f"playing_{prd['id']}"
                    if playing_key not in st.session_state:
                        st.session_state[playing_key] = False
                    
                    # 상세 페이지 링크 규칙
                    detail_url = f"https://www.halfclub.com/product/{prd['id']}"
                    
                    # 재생 중이고 동영상이 존재하면 비디오 플레이어를 상품 이미지 영역에 렌더링
                    if video_exists and st.session_state[playing_key]:
                        import base64
                        try:
                            with open(video_file_path, "rb") as vf:
                                b64 = base64.b64encode(vf.read()).decode()
                            st.markdown(
                                f'<div style="position: relative; width: 100%; aspect-ratio: 3/4; overflow: hidden; border-radius: 8px; border: 1px solid #eee; margin-bottom: 8px;">'
                                f'  <video autoplay loop muted playsinline style="width: 100%; height: 100%; object-fit: cover;">'
                                f'    <source src="data:video/webm;base64,{b64}" type="video/webm">'
                                f'  </video>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
                        except Exception as e:
                            st.video(video_file_path, format="video/webm", autoplay=True)
                    else:
                        if prd["img"]:
                            st.markdown(
                                f'<div style="position: relative; width: 100%; aspect-ratio: 3/4; overflow: hidden; border-radius: 8px; border: 1px solid #eee; margin-bottom: 8px;">'
                                f'  <a href="{detail_url}" target="_blank" style="display:block; width:100%; height:100%;">'
                                f'    <img src="{prd["img"]}" style="width:100%; height:100%; object-fit:cover;" title="새창으로 상세 상품 보기">'
                                f'  </a>'
                                + (
                                    f'  <div style="position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.6); padding: 4px 8px; border-radius: 4px; color: white; font-size: 11px; font-weight: bold; pointer-events: none;">'
                                    f'    🎬 생성 완료'
                                    f'  </div>' if video_exists else ''
                                ) +
                                f'</div>',
                                unsafe_allow_html=True
                            )
                    
                    st.caption(f"**[{prd['brand']}]** {prd['name']}")
                    if prd["price"]:
                        st.caption(f"가격: {prd['price']:,}원")
                    else:
                        st.caption(" ")
                    
                    if video_exists:
                        btn_col1, btn_col2 = st.columns([3, 1])
                        with btn_col1:
                            if st.session_state[playing_key]:
                                if st.button("🖼️ 이미지", key=f"stop_{prd['id']}", use_container_width=True):
                                    st.session_state[playing_key] = False
                                    st.rerun()
                            else:
                                if st.button("▶️ 재생", key=f"play_{prd['id']}", use_container_width=True):
                                    st.session_state[playing_key] = True
                                    st.rerun()
                        with btn_col2:
                            if st.button("🗑️", key=f"del_{prd['id']}", use_container_width=True, help="동영상 삭제"):
                                try:
                                    os.remove(video_file_path)
                                    st.session_state[playing_key] = False
                                    st.toast("동영상이 삭제되었습니다.")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"삭제 실패: {err}")
                                    
                        if st.button("선택", key=f"select_{prd['id']}", use_container_width=True):
                            st.session_state["selected_prd_id"] = prd["id"]
                            st.session_state["selected_prd_name"] = prd["name"]
                            st.rerun()
                    else:
                        if st.button("선택", key=f"select_{prd['id']}", use_container_width=True):
                            st.session_state["selected_prd_id"] = prd["id"]
                            st.session_state["selected_prd_name"] = prd["name"]
                            st.rerun()
    else:
        st.info("불러온 상품이 없습니다.")

with col2:
    st.subheader("🎬 동영상 생성")
    
    # 직접 입력하거나 리스트에서 선택된 값 표시
    if "selected_prd_id" in st.session_state:
        selected_prd_id = st.session_state["selected_prd_id"]
        st.info(f"선택된 상품: **{st.session_state['selected_prd_name']}** ({selected_prd_id})")
        if st.button("선택 초기화"):
            del st.session_state["selected_prd_id"]
            del st.session_state["selected_prd_name"]
            st.rerun()

    direct_product_no = st.text_input("상품 번호 직접 입력 (선택된 상품 없을 때 사용)", value=selected_prd_id or "")

    target_prd_id = direct_product_no.strip()

    # AI 생성 활성화 토글 (비용 절감용)
    use_ai = st.checkbox("🤖 AI 모델 워킹/회전 비디오 생성 활성화 (API 호출 비용 발생)", value=True)

    st.info(
        "💡 **API 할당량(Quota) 제한 안내**\n\n"
        "현재 구글 AI 스튜디오 Veo 모델의 분당 요청 제한(RPM)은 **최대 2회**로 매우 제한적입니다. "
        "따라서 한 번의 동영상 생성이 완료된 후 다음 상품 동영상을 만들 때는 **최소 30초 ~ 1분 이상의 시간 여유**를 두고 실행해 주시기 바랍니다. "
        "(일일 한도 RPD가 남아있더라도 연속으로 누르면 `429 RESOURCE_EXHAUSTED` 한계 에러가 발생합니다.)"
    )

    if st.button("🚀 동영상 생성 시작", type="primary", use_container_width=True):
        if not target_prd_id:
            st.warning("상품 번호를 입력하거나 리스트에서 선택해주세요.")
        else:
            with st.spinner(f"상품 번호 '{target_prd_id}'의 데이터를 수집하고 렌더링 중입니다... (1~2분 정도 소요됩니다)"):
                try:
                    # 영상 생성 함수 호출 (자막 없음, AI 연동 워킹 비디오 생성 지원)
                    api_key_to_pass = selected_api_key.strip() if (selected_api_key and use_ai) else None
                    openai_key_to_pass = openai_api_key.strip() if openai_api_key else None
                    output_video_path = generate_product_video(target_prd_id, api_key=api_key_to_pass, openai_key=openai_key_to_pass, video_model=video_model)
                    
                    if output_video_path and os.path.exists(output_video_path):
                        st.success("🎉 동영상 생성이 완료되었습니다!")
                        
                        # 생성된 비디오 렌더링 (9:16 비율로 가득 차게 구성)
                        import base64
                        try:
                            with open(output_video_path, 'rb') as video_file:
                                video_bytes = video_file.read()
                            b64_out = base64.b64encode(video_bytes).decode()
                            st.markdown(
                                f'<div style="width: 100%; aspect-ratio: 9/16; overflow: hidden; border-radius: 12px; border: 1px solid #ddd; background-color: #000; margin-bottom: 12px;">'
                                f'  <video autoplay loop muted playsinline style="width: 100%; height: 100%; object-fit: cover;">'
                                f'    <source src="data:video/webm;base64,{b64_out}" type="video/webm">'
                                f'  </video>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
                        except Exception as e:
                            st.video(output_video_path, format="video/webm", autoplay=True)
                        
                        with open(output_video_path, 'rb') as video_file:
                            video_bytes = video_file.read()
                        
                        # 다운로드 버튼 제공
                        st.download_button(
                            label="💾 동영상 다운로드",
                            data=video_bytes,
                            file_name=f"product_video_{target_prd_id}.webm",
                            mime="video/webm",
                            use_container_width=True
                        )
                        # 삭제 버튼 제공
                        if st.button("🗑️ 생성된 동영상 삭제", key=f"delete_right_{target_prd_id}", use_container_width=True):
                            try:
                                os.remove(output_video_path)
                                st.rerun()
                            except Exception as err:
                                st.error(f"삭제 실패: {err}")
                    else:
                        st.error("영상 생성은 완료되었으나, 파일을 찾을 수 없습니다.")
                        
                except Exception as e:
                    st.error(f"동영상 생성 중 오류가 발생했습니다: {e}")


