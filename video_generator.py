import os
import sys
import uuid
import tempfile
import urllib.request
import requests
from bs4 import BeautifulSoup
from moviepy import ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips, VideoFileClip
import moviepy.video.fx as vfx
import time

import google.generativeai as genai
from google import genai as google_genai_sdk
from google.genai import types
from openai import OpenAI

# 환경에 따라 ImageMagick 경로 설정이 필요할 수 있습니다.
# macOS 환경에서 brew로 설치한 경우 보통 아래와 같습니다.
# os.environ["IMAGEMAGICK_BINARY"] = "/opt/homebrew/bin/magick"

def generate_veo_video(image_path, api_key):
    """Google Veo 3.1 API를 호출하여 정적인 이미지를 모델 워킹 비디오로 변환합니다."""
    try:
        # 새로운 google-genai SDK의 Client 객체를 API Key와 함께 생성
        client = google_genai_sdk.Client(api_key=api_key)
        
        print("Veo API용 로컬 이미지 파일 로드 중...")
        with open(image_path, "rb") as f:
            img_bytes = f.read()
            
        mime_type = "image/jpeg"
        if image_path.lower().endswith(".png"):
            mime_type = "image/png"
        elif image_path.lower().endswith(".webp"):
            mime_type = "image/webp"
            
        img_obj = types.Image(image_bytes=img_bytes, mime_type=mime_type)
        
        print("Veo API에 비디오 생성 요청을 전송합니다...")
        operation = client.models.generate_videos(
            model="veo-3.1-lite-generate-preview",
            prompt="이 이미지의 옷을 똑같이 입은 전문 패션 모델이 우아하고 천천히 360도 회전(턴)하는 실사 동영상. 모델이 천천히 돌면서 옷의 앞태, 옆태, 뒤태를 모두 보여주며 의류의 핏, 스타일, 원단 재질의 디테일과 텍스처를 선명하게 노출합니다. 동영상 재생 내내 배경화면은 아무런 변화 없이 단일 톤의 '깨끗하고 고정된 회색 스튜디오 배경'으로 완벽하게 동일하게 유지되어야 하며, 카메라 무빙은 흔들림 없이 아주 부드럽고 천천히 줌인되며, 옷의 디자인과 색상, 패턴은 입력 이미지와 완벽하게 일치하고 왜곡이나 환각 현상이 없어야 합니다.",
            image=img_obj,
            config=types.GenerateVideosConfig(
                aspect_ratio="9:16",
                resolution="720p"
            )
        )
        
        print("Veo 비디오 생성 진행률 확인 중...")
        while not operation.done:
            print("비디오 생성 진행 중... (15초 후 재확인)")
            time.sleep(15)
            operation = client.operations.get(operation)
            
        generated_video = operation.response.generated_videos[0]
        
        # 파일 다운로드 (바이트 데이터를 수신하여 로컬 파일로 저장)
        print("생성된 Veo 비디오 다운로드 중...")
        video_bytes = client.files.download(file=generated_video.video)
        
        temp_video_path = tempfile.mktemp(suffix=".mp4")
        with open(temp_video_path, "wb") as f:
            f.write(video_bytes)
            
        print("Veo 비디오 생성 및 다운로드 완료!")
        return temp_video_path
        
    except Exception as e:
        print(f"Veo Video Generation Failed: {e}")
        raise e

def generate_luma_video(image_url, api_key):
    """Luma Dream Machine API를 호출하여 정적인 이미지를 모델 워킹 비디오로 변환합니다."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": "이 이미지의 옷을 똑같이 입은 전문 패션 모델이 우아하고 천천히 360도 회전(턴)하는 실사 동영상. 모델이 천천히 돌면서 옷의 앞태, 옆태, 뒤태를 모두 보여주며 의류의 핏, 스타일, 원단 재질의 디테일과 텍스처를 선명하게 노출합니다. 동영상 재생 내내 배경화면은 아무런 변화 없이 단일 톤의 '깨끗하고 고정된 회색 스튜디오 배경'으로 완벽하게 동일하게 유지되어야 하며, 카메라 무빙은 흔들림 없이 아주 부드럽고 천천히 줌인되며, 옷의 디자인과 색상, 패턴은 입력 이미지와 완벽하게 일치하고 왜곡이나 환각 현상이 없어야 합니다.",
        "keyframes": {
            "frame0": {
                "type": "image",
                "url": image_url
            }
        }
    }
    
    print("Luma API에 비디오 생성 요청을 전송합니다...")
    response = requests.post("https://api.lumalabs.ai/dream-machine/v1/generations", json=payload, headers=headers, timeout=15)
    response.raise_for_status()
    gen_id = response.json().get("id")
    
    print(f"비디오 생성 시작 (ID: {gen_id}). 진행률을 확인하는 중...")
    while True:
        status_resp = requests.get(f"https://api.lumalabs.ai/dream-machine/v1/generations/{gen_id}", headers=headers, timeout=10)
        status_resp.raise_for_status()
        status_data = status_resp.json()
        state = status_data.get("state")
        
        if state == "completed":
            video_url = status_data.get("assets", {}).get("video")
            print("비디오 생성 완료!")
            return video_url
        elif state == "failed":
            raise Exception(f"Luma AI가 비디오 생성에 실패했습니다: {status_data.get('failure_reason')}")
        
        print("비디오 생성 진행 중... (10초 후 재확인)")
        time.sleep(10)

def download_video(url, output_dir):
    """생성된 AI 비디오 파일을 로컬 임시 폴더에 다운로드합니다."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            filename = os.path.join(output_dir, f"{uuid.uuid4().hex}.mp4")
            with open(filename, 'wb') as f:
                f.write(response.read())
            return filename
    except Exception as e:
        print(f"비디오 다운로드 실패: {e}")
        return None

def fetch_product_data(product_no):
    """API를 호출하여 상품 데이터를 수집합니다."""
    url = f"https://hapix.halfclub.com/product/products/withoutPrice/{product_no}?countryCd=001&langCd=001&siteCd=1&deviceCd=001"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    product_data = data.get("data")
    if not product_data:
        raise Exception(f"API Error: Data is null (errorCode: {data.get('errorCode')})")
    prod_image_info = product_data.get("productImage", {}) or {}
    
    main_image = product_data.get("basicExtNm") or prod_image_info.get("basicExtNm")
    if main_image and not main_image.startswith("http"):
        main_image = "https://cdn2.halfclub.com/" + main_image
    
    additional_images = []
    if prod_image_info:
        for i in range(1, 10):
            img_url = prod_image_info.get(f"add{i}ExtNm")
            if img_url:
                if not img_url.startswith("http"):
                    img_url = "https://cdn2.halfclub.com/" + img_url
                additional_images.append(img_url)
                
    description_html = product_data.get("productDesc", {}).get("prdDescContClob", "")
    
    return {
        "main_image": main_image,
        "additional_images": additional_images,
        "description_html": description_html
    }

def generate_vlm_subtitles(html_content, api_key, vlm_type="Gemini"):
    """VLM API를 사용하여 매력적인 숏폼 자막 3개를 생성합니다. (Gemini 또는 GPT-4o 지원)"""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        text_content = soup.get_text(separator=' ', strip=True)
        
        prompt = f"""
        다음은 쇼핑몰 상품의 상세 설명 텍스트입니다:
        ---
        {text_content[:2000]}
        ---
        위 내용을 바탕으로 인스타그램 릴스나 틱톡에 어울리는 짧고 매력적인 
        홍보 자막(각각 15자 이내) 3개를 작성해주세요. 
        반드시 번호나 특수기호 없이 줄바꿈으로만 3문장을 출력해주세요.
        """

        raw_text = None
        if vlm_type == "GPT-4o":
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful marketing assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            raw_text = response.choices[0].message.content
        else:  # Gemini
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            raw_text = response.text

        if raw_text:
            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
            cleaned_lines = []
            for line in lines:
                # 불필요한 번호표기나 기호 제거
                line = line.lstrip('1234567890.-* )')
                if line:
                    cleaned_lines.append(line)
            
            if len(cleaned_lines) >= 3:
                return cleaned_lines[:3]
            elif len(cleaned_lines) > 0:
                return cleaned_lines
    except Exception as e:
        print(f"VLM API 오류 ({vlm_type} -> 기본 파싱으로 대체): {e}")
        
    return None

def parse_html_description(html_content):
    """상세 HTML에서 텍스트와 추가 이미지 URL을 추출합니다."""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 텍스트 추출 (주요 특징, 재질 등)
    texts = []
    for tag in soup.find_all(['p', 'span', 'div']):
        text = tag.get_text(strip=True)
        # 너무 짧거나 긴 텍스트 제외하여 핵심 문구 위주로 추출
        if text and 5 <= len(text) <= 30:
            texts.append(text)
            
    # 중복 제거
    texts = list(dict.fromkeys(texts))
    
    # 이미지 추출 및 설명/스펙 이미지 필터링
    detail_images = []
    exclude_keywords = [
        "size", "guide", "notice", "delivery", "caution", "washing", "spec", "table", 
        "banner", "info", "wash", "event", "intro", "coupon", "map", "detail_info",
        "배송", "사이즈", "스펙", "안내", "공지", "세탁", "주의", "이벤트", "배너", "가이드",
        "쿠폰", "지도", "상세정보", "교환", "반품"
    ]
    
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif not src.startswith("http"):
                src = "https://cdn2.halfclub.com/" + src
            
            # 설명/스펙/공지 관련 이미지인지 키워드 검사
            url_lower = src.lower()
            should_exclude = False
            for kw in exclude_keywords:
                if kw in url_lower:
                    should_exclude = True
                    break
            
            if not should_exclude:
                detail_images.append(src)
            
    return texts, detail_images

def download_image(url, output_dir):
    """이미지를 다운로드하여 로컬에 저장합니다."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            filename = os.path.join(output_dir, f"{uuid.uuid4().hex}.jpg")
            with open(filename, 'wb') as f:
                f.write(response.read())
            
            # 다운로드된 파일이 유효한지(크기가 0보다 큰지) 검증
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return filename
            else:
                if os.path.exists(filename):
                    os.remove(filename)
                return None
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None

def prepare_clip(image_path, target_size=(1080, 1920), duration=2, face_box=None):
    """이미지를 지정된 해상도로 자르고 리사이징하여 비디오 클립으로 만듭니다.
    얼굴 바운딩 박스가 지정되면 얼굴이 잘리지 않도록 조정하여 크롭합니다.
    """
    clip = ImageClip(image_path)
    
    w, h = clip.size
    target_w, target_h = target_size
    
    aspect_image = w / h
    aspect_target = target_w / target_h
    
    if aspect_image > aspect_target:
        # 이미지가 더 넓은 경우: 높이를 맞추고 가로를 자름
        clip = clip.resized(height=target_h)
        new_w = clip.size[0]
        
        if face_box and "xmin" in face_box and "xmax" in face_box:
            # face_box에 맞추어 가로 크롭 중앙을 결정
            face_x_center = ((face_box["xmin"] + face_box["xmax"]) / 2) * new_w
            x1 = int(face_x_center - target_w / 2)
            x2 = x1 + target_w
            
            # 바운더리 체크
            if x1 < 0:
                x1 = 0
                x2 = target_w
            elif x2 > new_w:
                x2 = new_w
                x1 = new_w - target_w
            clip = clip.cropped(x1=int(x1), y1=0, x2=int(x2), y2=target_h)
        else:
            x_center = int(new_w / 2)
            clip = clip.cropped(x1=x_center - int(target_w/2), y1=0, x2=x_center + int(target_w/2), y2=target_h)
    else:
        # 이미지가 더 높은 경우: 너비를 맞추고 세로를 자름
        clip = clip.resized(width=target_w)
        new_h = clip.size[1]
        
        if face_box and "ymin" in face_box and "ymax" in face_box:
            # face_box에 맞추어 세로 크롭 범위를 조절하여 얼굴이 잘리지 않게 함
            face_ymin_pixel = face_box["ymin"] * new_h
            face_ymax_pixel = face_box["ymax"] * new_h
            
            # 얼굴 중심에 포커스
            face_y_center = (face_ymin_pixel + face_ymax_pixel) / 2
            y1 = int(face_y_center - target_h / 2)
            y2 = y1 + target_h
            
            # 바운더리 체크
            if y1 < 0:
                y1 = 0
                y2 = target_h
            elif y2 > new_h:
                y2 = new_h
                y1 = new_h - target_h
                
            # 얼굴 영역이 잘려나가는지 재검증 후 조절
            if face_ymin_pixel < y1:
                y1 = max(0, int(face_ymin_pixel - 20))
                y2 = y1 + target_h
                if y2 > new_h:
                    y2 = new_h
                    y1 = new_h - target_h
            elif face_ymax_pixel > y2:
                y2 = min(new_h, int(face_ymax_pixel + 20))
                y1 = y2 - target_h
                if y1 < 0:
                    y1 = 0
                    y2 = target_h
                    
            clip = clip.cropped(x1=0, y1=int(y1), x2=target_w, y2=int(y2))
        else:
            # face_box가 없을 경우에도 9:16 인물 크롭 컷을 배려해 약간 위쪽 중심(0.4)으로 자름
            y_center = int(new_h * 0.4)
            y1 = y_center - int(target_h/2)
            y2 = y1 + target_h
            if y1 < 0:
                y1 = 0
                y2 = target_h
            elif y2 > new_h:
                y2 = new_h
                y1 = new_h - target_h
            clip = clip.cropped(x1=0, y1=int(y1), x2=target_w, y2=int(y2))
    return clip.with_duration(duration)

def prepare_video_clip(clip, target_size=(1080, 1920)):
    """비디오 클립을 지정된 해상도로 자르고 리사이징합니다."""
    w, h = clip.size
    target_w, target_h = target_size
    aspect_video = w / h
    aspect_target = target_w / target_h
    
    if aspect_video > aspect_target:
        clip = clip.resized(height=target_h)
        new_w = clip.size[0]
        x_center = new_w / 2
        clip = clip.cropped(x1=x_center - target_w/2, y1=0, x2=x_center + target_w/2, y2=target_h)
    else:
        clip = clip.resized(width=target_w)
        new_h = clip.size[1]
        y_center = new_h / 2
        clip = clip.cropped(x1=0, y1=y_center - target_h/2, x2=target_w, y2=y_center + target_h/2)
    return clip

def process_and_crop_image_with_openai(image_path, openai_key, return_face_box=False):
    """
    OpenAI gpt-4o-mini 비전 모델을 사용하여 이미지를 분석합니다.
    1. 패션 모델이 포함되어 있는지 확인합니다. (모델이 없는 이미지는 제외하기 위해 False 반환)
    2. 이미지에 텍스트 영역이 있다면, 모델이 포함된 깨끗한 영역의 정규화된 바운딩 박스(0.0 ~ 1.0)를 반환받아 잘라냅니다.
    3. 대표이미지에서 모델 얼굴이 감지되면 영상에서 얼굴이 잘리지 않도록 face_box를 함께 반환할 수 있습니다.
    """
    if not openai_key:
        return (image_path, None) if return_face_box else image_path
        
    try:
        import base64
        import json
        from openai import OpenAI
        from PIL import Image
        
        # 이미지 base64 인코딩
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")
            
        client = OpenAI(api_key=openai_key)
        
        # gpt-4o-mini 비전 분석 (JSON 모드로 결과 수신)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Analyze this product image and return a JSON object with the following fields:\n"
                                "1. 'has_model': true if a human fashion model or mannequin wearing the clothes is present in the image, false otherwise.\n"
                                "2. 'has_text': true if there is any written text, specifications, notice, or sizing chart overlay in the image, false otherwise.\n"
                                "3. 'crop_box': if 'has_model' is true, specify a bounding box that contains ONLY the model and the clothing, completely cropping out and excluding any text or banners. Specify normalized coordinates between 0.0 and 1.0 as a dictionary with 'ymin', 'xmin', 'ymax', 'xmax'. If there is no text, specify the entire image (i.e., {'ymin': 0.0, 'xmin': 0.0, 'ymax': 1.0, 'xmax': 1.0}).\n"
                                "4. 'has_face': true if the human fashion model's face is clearly visible in the image, false otherwise.\n"
                                "5. 'face_box': if 'has_face' is true, specify the bounding box containing the model's face (excluding hair or neck as much as possible, just the face area). Specify normalized coordinates between 0.0 and 1.0 as a dictionary with 'ymin', 'xmin', 'ymax', 'xmax'.\n"
                                "\n"
                                "Return JSON format example:\n"
                                "{\n"
                                "  \"has_model\": true,\n"
                                "  \"has_text\": false,\n"
                                "  \"crop_box\": {\"ymin\": 0.0, \"xmin\": 0.0, \"ymax\": 1.0, \"xmax\": 1.0},\n"
                                "  \"has_face\": true,\n"
                                "  \"face_box\": {\"ymin\": 0.1, \"xmin\": 0.45, \"ymax\": 0.2, \"xmax\": 0.55}\n"
                                "}"
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        
        result_content = response.choices[0].message.content
        data = json.loads(result_content)
        print(f"OpenAI 이미지 분석 결과 [{os.path.basename(image_path)}]: {data}")
        
        if not data.get("has_model", False):
            print(f"-> 모델 미검출로 이미지 제외: {image_path}")
            return (None, None) if return_face_box else None
            
        crop_box = data.get("crop_box")
        has_crop = crop_box and (data.get("has_text", False) or crop_box["ymin"] > 0.0 or crop_box["xmin"] > 0.0 or crop_box["ymax"] < 1.0 or crop_box["xmax"] < 1.0)
        
        if has_crop:
            print(f"-> 텍스트 영역 크롭 시작: {crop_box}")
            pil_img = Image.open(image_path)
            width, height = pil_img.size
            
            ymin = int(crop_box["ymin"] * height)
            xmin = int(crop_box["xmin"] * width)
            ymax = int(crop_box["ymax"] * height)
            xmax = int(crop_box["xmax"] * width)
            
            # 범위 검증
            ymin = max(0, min(ymin, height - 1))
            xmin = max(0, min(xmin, width - 1))
            ymax = max(ymin + 10, min(ymax, height))
            xmax = max(xmin + 10, min(xmax, width))
            
            cropped_img = pil_img.crop((xmin, ymin, xmax, ymax))
            cropped_img.save(image_path)
            print(f"-> 텍스트 영역 잘라내기 완료 및 저장: {image_path} (크기: {cropped_img.size})")
            
        # 얼굴 영역 반환 처리 및 좌표 변환
        face_box = None
        if data.get("has_face", False) and data.get("face_box"):
            orig_face = data.get("face_box")
            if has_crop:
                # 크롭된 경우 상대 좌표 계산
                c_ymin, c_xmin, c_ymax, c_xmax = crop_box["ymin"], crop_box["xmin"], crop_box["ymax"], crop_box["xmax"]
                denom_y = c_ymax - c_ymin if (c_ymax - c_ymin) > 0 else 1.0
                denom_x = c_xmax - c_xmin if (c_xmax - c_xmin) > 0 else 1.0
                face_box = {
                    "ymin": max(0.0, min(1.0, (orig_face["ymin"] - c_ymin) / denom_y)),
                    "xmin": max(0.0, min(1.0, (orig_face["xmin"] - c_xmin) / denom_x)),
                    "ymax": max(0.0, min(1.0, (orig_face["ymax"] - c_ymin) / denom_y)),
                    "xmax": max(0.0, min(1.0, (orig_face["xmax"] - c_xmin) / denom_x))
                }
            else:
                face_box = orig_face
                
        return (image_path, face_box) if return_face_box else image_path
    except Exception as e:
        print(f"OpenAI 이미지 처리 에러: {e}")
        return (image_path, None) if return_face_box else image_path

def generate_product_video(product_no, api_key=None, openai_key=None, video_model="Luma Dream Machine"):
    output_dir = "output_videos"
    os.makedirs(output_dir, exist_ok=True)
    output_filename = os.path.join(output_dir, f"result_{product_no}.webm")
    if os.path.exists(output_filename):
        print(f"=== 캐시된 동영상 발견: {output_filename}을 재사용합니다. ===")
        return output_filename

    print(f"=== 시작: 상품 번호 {product_no} 영상 생성 ===")
    
    temp_dir = tempfile.mkdtemp()
    print(f"임시 작업 폴더 생성: {temp_dir}")
    
    try:
        # 1. API 데이터 수집
        print("1. 상품 데이터 수집 중...")
        data = fetch_product_data(product_no)
        
        main_image_url = data["main_image"]
        additional_image_urls = data["additional_images"]
        html_desc = data["description_html"]
        
        # 2. HTML 파싱 및 이미지 리스트 준비
        print("2. 상품 상세 정보 파싱 중...")
        features_text, detail_image_urls = parse_html_description(html_desc)
        
        # 3. 이미지 다운로드 및 OpenAI 분석/크롭 필터링
        print("3. 이미지 리소스 다운로드 및 텍스트/모델 분석 중...")
        main_img_path = download_image(main_image_url, temp_dir)
        
        # 메인 이미지에 텍스트가 있으면 잘라냅니다.
        face_box = None
        if main_img_path and openai_key:
            main_img_path, face_box = process_and_crop_image_with_openai(main_img_path, openai_key, return_face_box=True)
        
        add_img_paths = []
        # 전후좌우 및 다양한 핏을 노출하기 위해 최대 8장 다운로드 후 필터링
        for url in additional_image_urls[:8]:
            path = download_image(url, temp_dir)
            if path:
                if openai_key:
                    processed_path = process_and_crop_image_with_openai(path, openai_key)
                    if processed_path:
                        add_img_paths.append(processed_path)
                    else:
                        if os.path.exists(path): os.remove(path)
                else:
                    add_img_paths.append(path)
            
        # 상품상세이미지는 참고하지 않으므로 detail_img_paths를 빈 리스트로 설정하고 다운로드를 건너뜁니다.
        detail_img_paths = []
            
        # 4. 동영상 클립 구성
        print("4. 동영상 렌더링 준비 중...")
        target_resolution = (1080, 1920)
        clips = []
        
        # Scene 1: 대표 이미지 활용 인트로
        animated_intro_path = None
        if api_key:
            if video_model in ["Google Veo 3.1", "Google Veo 3.1 Lite"] and main_img_path:
                try:
                    print("Google Veo 3.1 API를 사용하여 살아 움직이는 모델 워킹 영상 생성 중...")
                    animated_intro_path = generate_veo_video(main_img_path, api_key)
                except Exception as veo_err:
                    try:
                        import streamlit as st
                        st.warning(f"⚠️ Google Veo 3.1 모델 호출 실패 (정적 이미지 슬라이드쇼로 대체됩니다): {veo_err}")
                    except Exception:
                        pass
                    print(f"Google Veo 모델 워킹 비디오 생성 오류 (스틸 이미지로 대체): {veo_err}")
            elif video_model == "Luma Dream Machine" and main_image_url:
                try:
                    print("Luma Dream Machine API를 사용하여 살아 움직이는 모델 워킹 영상 생성 중...")
                    luma_video_url = generate_luma_video(main_image_url, api_key)
                    if luma_video_url:
                        animated_intro_path = download_video(luma_video_url, temp_dir)
                except Exception as luma_err:
                    try:
                        import streamlit as st
                        st.warning(f"⚠️ Luma Dream Machine 호출 실패 (정적 이미지 슬라이드쇼로 대체됩니다): {luma_err}")
                    except Exception:
                        pass
                    print(f"Luma AI 모델 워킹 비디오 생성 오류 (스틸 이미지로 대체): {luma_err}")
        
        if animated_intro_path and os.path.exists(animated_intro_path):
            print("생성된 AI 모델 워킹/회전 비디오를 연동합니다.")
            video_clip = VideoFileClip(animated_intro_path)
            video_clip = prepare_video_clip(video_clip, target_resolution)
            clips.append(video_clip)
            
            # 총 재생 시간 10초를 맞추기 위한 로직
            # AI 비디오 길이를 L이라 할 때, 추가 이미지 클립 K개(2개)를 넣는다면:
            # L + K * d - 0.5 * K = 10.0 => K * d = 10.0 - L + 0.5 * K => d = (10.0 - L) / K + 0.5
            L = video_clip.duration
            if L >= 10.0:
                # 만약 AI 비디오가 10초 이상이면 10초로 자르고 그것만 사용
                try:
                    video_clip = video_clip.subclipped(0, 10.0)
                except AttributeError:
                    video_clip = video_clip.subclip(0, 10.0)
                clips = [video_clip]
            else:
                K = 2
                d = (10.0 - L) / K
                if d < 1.0:
                    d = 1.0
                
                # 상세 이미지를 제외하므로 추가 이미지(add_img_paths)만 사용
                focus_paths = add_img_paths[:K]
                while len(focus_paths) < K and main_img_path:
                    focus_paths.append(main_img_path)
                
                image_clips = []
                for img_path in focus_paths:
                    current_face_box = face_box if img_path == main_img_path else None
                    clip = prepare_clip(img_path, target_resolution, duration=d, face_box=current_face_box)
                    image_clips.append(clip)
                
                clips = [video_clip] + image_clips
        else:
            # Fallback: 스틸 이미지 슬라이드쇼 연출 (정확히 10초 재생)
            print("AI 비디오 생성 실패 또는 비활성화로 인해, 스틸 이미지 슬라이드쇼로 대체합니다.")
            all_img_paths = []
            if main_img_path:
                all_img_paths.append(main_img_path)
            all_img_paths.extend(add_img_paths)
            
            all_img_paths = [p for p in all_img_paths if p and os.path.exists(p)]
            
            if not all_img_paths:
                raise Exception("비디오를 생성할 이미지가 없습니다.")
            
            # 최대 4개 이미지 사용
            M = min(4, len(all_img_paths))
            if M < 2:
                # 1장만 있는 경우 10초짜리 단일 클립
                clip = prepare_clip(all_img_paths[0], target_resolution, duration=10.0, face_box=face_box)
                clips = [clip]
            else:
                d = 10.0 / M
                for idx, img_path in enumerate(all_img_paths[:M]):
                    current_face_box = face_box if img_path == main_img_path else None
                    clip = prepare_clip(img_path, target_resolution, duration=d, face_box=current_face_box)
                    clips.append(clip)
            
        if not clips:
            raise Exception("비디오 클립을 생성할 유효한 이미지가 없습니다.")
            
        # 클립들을 깜빡임 없이 매끄럽게 겹침 없이 병합
        print("5. 최종 동영상 인코딩 중... (시간이 소요될 수 있습니다)")
        final_video = concatenate_videoclips(clips, padding=0, method="compose")
        
        output_filename = os.path.join(output_dir, f"result_{product_no}.webm")
        final_video.write_videofile(
            output_filename, 
            fps=24, 
            codec="libvpx-vp9", 
            audio=False
        )
        print(f"\n=== 성공: 동영상 생성 완료 -> {output_filename} ===")
        
        return output_filename
        
    except Exception as e:
        print(f"\n동영상 생성 중 오류 발생: {e}")
        raise e
        
if __name__ == "__main__":
    if len(sys.argv) > 1:
        product_no = sys.argv[1]
        generate_product_video(product_no)
    else:
        print("사용법: python video_generator.py <상품번호>")
        print("예시: python video_generator.py 1234567")
