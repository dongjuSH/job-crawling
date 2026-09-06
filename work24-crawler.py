"""
고용24(work24.go.kr) 채용정보 크롤러 - 프로토타입
- 서버사이드 렌더링 페이지를 대상으로 requests + BeautifulSoup 사용
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
from datetime import datetime

BASE_URL = "https://m.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do"

HEADERS = {
    # 실제 브라우저처럼 보이기 위한 User-Agent 설정
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://m.work24.go.kr/",
}

# F12 Network 탭에서 캡처한 실제 파라미터 중, 우리가 실제로 값을 채워 쓰는 것만 추림.
BASE_PARAMS = {
    "occupation": "106,107,025,026,024,023,022",  # IT 직종 코드
    "occupationParam": "106,107,025,026,024,023,022",
    "codeDepth1Info": "11000",  # 서울
    "codeDepth2Info": "11000",
    "region": "11000",
    "regionParam": "11000",
    "resultCnt": "100",  # 페이지당 결과 수
    "currentPageNo": "1",  # run_crawler에서 매번 덮어씀
    "pageIndex": "1",  # run_crawler에서 매번 덮어씀
    "sortField": "DATE",
    "sortOrderBy": "DESC",
    "siteClcd": "all",  # 전체 정보제공처
    "searchMode": "Y",
    "academicGbnoEdu": "noEdu",  # 원본 요청에 값이 있었던 필드 (정확한 의미 미확인, 안전하게 유지)
    "benefitSrchAndOr": "O",  # 원본 요청에 값이 있었던 필드 (정확한 의미 미확인, 안전하게 유지)
}


def fetch_list_page(params: dict) -> BeautifulSoup:
    """채용정보 목록 페이지 요청 후 파싱"""
    response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=10)
    response.raise_for_status()
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def extract_jobs(soup: BeautifulSoup) -> list[dict]:
    """
    목록 페이지 HTML에서 공고 정보 추출.
    클래스명을 확신할 수 없으므로, 확실히 존재하는 단서
    (상세페이지로 가는 <a href="...empDetailAuthView.do...">)를 기준으로
    그 링크를 감싸는 행(tr 또는 li)을 거슬러 올라가 텍스트를 통째로 수집하는 방식.
    -> 이렇게 하면 정확한 클래스명을 몰라도 어느 정도 동작함.
    실행 후 결과가 이상하면 rows[0]를 print()해서 실제 구조를 보고 다듬어야 함.
    """
    jobs = []

    detail_links = soup.select("a[href*='empDetailAuthView']")

    for link_elem in detail_links:
        try:
            # 링크를 감싸는 가장 가까운 tr(표 행) 또는 li(목록 항목) 찾기
            container = link_elem.find_parent("tr") or link_elem.find_parent("li")
            if container is None:
                continue

            title = link_elem.get_text(strip=True)
            href = link_elem.get("href", "")
            link = f"https://m.work24.go.kr{href}" if href.startswith("/") else href

            # wantedAuthNo를 공고 고유 ID로 추출 (DB 저장 시 중복 방지용 키로 유용)
            wanted_auth_no = None
            if "wantedAuthNo=" in href:
                wanted_auth_no = href.split("wantedAuthNo=")[1].split("&")[0]

            # 정보제공처(원본 출처) 로고 alt 텍스트로 판별
            source_elem = container.select_one("img[alt*='정보제공처']")
            source = (
                source_elem.get("alt", "").replace("정보제공처 ", "")
                if source_elem
                else "고용24"
            )

            # 행 전체 텍스트 (회사명/조건/마감일 등이 뒤섞여 있음 -> 추후 정규식/분리 필요)
            full_text = clean_text(container.get_text(separator=" | ", strip=True))

            jobs.append(
                {
                    "wanted_auth_no": wanted_auth_no,
                    "title": title,
                    "source": source,
                    "link": link,
                    "raw_row_text": full_text,  # 1차 수집 단계: 원문 그대로 저장, 이후 정제
                    "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception as e:
            print(f"⚠️ 파싱 실패: {e}")
            continue

    return jobs


DETAIL_HEADERS = {
    # 상세페이지는 목록 페이지와 달리 Referer가 없으면 막힐 수 있어 목록 URL을 Referer로 지정
    "User-Agent": HEADERS["User-Agent"],
    "Referer": BASE_URL,
}

# 제목에서 스킬을 찾을 때 쓸 키워드 사전
# 필요에 따라 팀에서 계속 추가/수정하면 됨 (대소문자 무시하고 매칭)
# ※ 이 사전에 있는 단어가 "제목"에 그대로 등장해야만 잡힘 (본문/자격요건 텍스트는 대상 아님)
SKILL_KEYWORDS = [
    # 프론트엔드
    "React",
    "Next.js",
    "Vue",
    "Vue.js",
    "Nuxt",
    "Angular",
    "Svelte",
    "TypeScript",
    "JavaScript",
    "jQuery",
    "HTML",
    "CSS",
    "SASS",
    "SCSS",
    # 백엔드 언어/프레임워크
    "Java",
    "Spring",
    "SpringBoot",
    "Kotlin",
    "Python",
    "Django",
    "FastAPI",
    "Flask",
    "Node.js",
    "Nest.js",
    "Express",
    "Go",
    "Golang",
    "Rust",
    "C++",
    "C#",
    ".NET",
    "PHP",
    "Laravel",
    "Ruby",
    "Rails",
    "Scala",
    "Elixir",
    # 모바일
    "iOS",
    "Android",
    "Swift",
    "Kotlin",
    "Flutter",
    "React Native",
    "Unity",
    "Unreal",
    # 클라우드/인프라
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "K8s",
    "Terraform",
    "Jenkins",
    "CI/CD",
    "Nginx",
    "Linux",
    "MSA",
    "마이크로서비스",
    # 데이터베이스
    "MySQL",
    "PostgreSQL",
    "MongoDB",
    "Redis",
    "Oracle",
    "MariaDB",
    "Elasticsearch",
    "DynamoDB",
    "Firebase",
    "Supabase",
    # 데이터/AI
    "AI",
    "ML",
    "머신러닝",
    "딥러닝",
    "인공지능",
    "데이터분석",
    "데이터엔지니어",
    "빅데이터",
    "TensorFlow",
    "PyTorch",
    "Spark",
    "Hadoop",
    "Airflow",
    "데이터사이언티스트",
    "MLOps",
    "LLM",
    "생성형AI",
    "챗봇",
    # API/아키텍처
    "API",
    "REST",
    "RESTful",
    "GraphQL",
    "gRPC",
    "Kafka",
    "MQTT",
    # 직무명 자체
    "프론트엔드",
    "백엔드",
    "풀스택",
    "풀스택개발자",
    "웹개발자",
    "앱개발자",
    "서버개발자",
    "DBA",
    "데이터베이스관리자",
    "인프라엔지니어",
    # 보안/네트워크
    "보안",
    "정보보안",
    "네트워크",
    "방화벽",
    "모의해킹",
    "침해대응",
    # QA/기타
    "QA",
    "테스터",
    "DevOps",
    "SRE",
    "임베디드",
    "IoT",
    "RPA",
    "블록체인",
    "게임개발",
    "그래픽스",
    "빅데이터엔지니어",
    "ETL",
    "BI",
]

# 급여가 숫자로 안 나오고 카테고리로 표시되는 대표적인 패턴들
SALARY_CATEGORY_PATTERNS = [
    "회사내규에 따름",
    "회사내규",
    "면접 후 결정",
    "면접후결정",
    "협의",
    "추후협의",
    "추후 결정",
    "-",
]


def extract_skills_from_title(title: str) -> list[str]:
    """제목 텍스트에서 SKILL_KEYWORDS에 매칭되는 키워드를 뽑아 리스트로 반환"""
    if not title:
        return []
    found = []
    lowered = title.lower()
    for kw in SKILL_KEYWORDS:
        if kw.lower() in lowered:
            found.append(kw)
    return found


def categorize_salary(raw_salary: str) -> dict:
    """
    급여 원문 텍스트를 숫자형/카테고리형으로 분리.
    반환 예시:
      {"type": "amount", "value": 2750000, "raw": "월 2,750,000원"}
      {"type": "category", "value": "회사내규에 따름", "raw": "회사내규에 따름"}
    """
    if not raw_salary or raw_salary.strip() in ("", "-"):
        return {"type": "unknown", "value": None, "raw": raw_salary}

    text = raw_salary.strip()

    for pat in SALARY_CATEGORY_PATTERNS:
        if pat in text:
            return {"type": "category", "value": pat, "raw": text}

    # "2,750,000원" 같은 순수 숫자 패턴 추출 시도
    import re

    match = re.search(r"[\d,]{4,}", text)
    if match:
        amount = int(match.group().replace(",", ""))
        return {"type": "amount", "value": amount, "raw": text}

    # 숫자도 카테고리 패턴도 아니면 텍스트 그대로 카테고리 취급
    return {"type": "category", "value": text, "raw": text}


def clean_text(text: str) -> str:
    """
    \\r, \\n, \\t 및 연속 공백을 정리해서 사람이 읽기 좋은 한 줄로 만듦.
    예: "경력\\r\\n\\t\\t(최소 10년\\r\\n\\t\\t이상)" -> "경력 (최소 10년 이상)"
    """
    if not text:
        return text
    import re

    # 개행/탭을 공백으로 치환 후, 연속된 공백을 하나로 축약
    cleaned = re.sub(r"[\r\n\t]+", " ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def parse_key_value_tables(soup: BeautifulSoup) -> dict:
    """
    상세페이지의 모든 <table>을 훑어서 th(항목명)-td(값) 쌍을 dict로 모음.
    한 행에 항목이 2쌍(모집직종/모집인원처럼) 있는 경우도 처리.
    페이지 템플릿이 조금씩 달라도 이 방식이면 대체로 잡힘.
    값은 clean_text로 정제해서 저장.
    """
    result = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            headers = row.find_all("th")
            cells = row.find_all("td")
            for h, c in zip(headers, cells):
                key = h.get_text(strip=True)
                val = clean_text(c.get_text(" ", strip=True))
                if key:
                    result[key] = val
    return result


def fetch_detail(wanted_auth_no: str, info_type_cd: str, info_type_group: str) -> dict:
    """
    상세페이지 요청 후 구조화 필드 추출.
    실패해도 크롤러 전체가 멈추지 않도록 예외를 잡아서 빈 dict 반환.
    """
    detail_url = "https://m.work24.go.kr/wk/a/b/1500/empDetailAuthView.do"
    params = {
        "wantedAuthNo": wanted_auth_no,
        "infoTypeCd": info_type_cd,
        "infoTypeGroup": info_type_group,
    }
    try:
        response = requests.get(
            detail_url, params=params, headers=DETAIL_HEADERS, timeout=10
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        # 조회수 (span.count 안의 숫자)
        view_count = None
        count_elem = soup.select_one(".count strong")
        if count_elem:
            try:
                view_count = int(count_elem.get_text(strip=True))
            except ValueError:
                pass

        kv = parse_key_value_tables(soup)

        return {
            "view_count": view_count,
            "recruit_headcount": kv.get("모집 인원"),
            "career_detail": kv.get("경력"),
            "education_detail": kv.get("학력"),
            "employment_type": kv.get("고용형태"),
            "work_location": kv.get("근무 예정지"),
            "salary_raw": kv.get("임금조건"),
            "salary_parsed": categorize_salary(kv.get("임금조건", "")),
            "preferred_condition": kv.get("우대조건"),
            "company_size_workers": kv.get("근로자수"),
            "company_capital": kv.get("자본금"),
            "company_revenue": kv.get("연매출액"),
            "company_industry": kv.get("업종"),
            "external_apply_url": extract_external_apply_url(
                soup
            ),  # "채용정보 제공 사이트 바로가기" 링크
        }
    except Exception as e:
        print(f"  ⚠️ 상세페이지 실패 ({wanted_auth_no}): {e}")
        return {}


def extract_external_apply_url(soup: BeautifulSoup) -> str:
    """
    work24 상세페이지의 "채용정보 제공 사이트 바로가기" 버튼에서
    f_goMove('URL') 형태로 심어진 원본 사이트 링크를 추출.
    (일반 href가 아니라 onclick 자바스크립트 안에 URL이 들어있는 구조)
    """
    import re

    for a in soup.find_all("a", onclick=True):
        match = re.search(r"f_goMove\('([^']+)'\)", a["onclick"])
        if match:
            return match.group(1)
    return None


def extract_ld_json_salary(soup: BeautifulSoup) -> dict:
    """
    인크루트 페이지에 심어진 <script type="application/ld+json"> (Schema.org JobPosting)에서
    baseSalary를 추출. 급여를 숫자로 공개한 공고는 여기에 minValue/maxValue가 깔끔하게 들어있음
    (급여 비공개 공고는 이 필드 자체가 없음).

    ※ 주의: minValue/maxValue가 실제 원(KRW) 단위가 아니라 "만원" 단위 숫자를 그대로 넣은 것으로
       추정됨 (예: minValue=5000은 5,000만원을 의미, 5,000원이 아님). 자동 환산하지 않고
       "만원 단위로 추정"이라는 걸 결과에 표시만 해둠 — 실제 단위 표준 준수 여부는 검증 안 됨.
    """
    import json as json_lib

    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json_lib.loads(script.string)
        except (json_lib.JSONDecodeError, TypeError):
            continue

        base_salary = data.get("baseSalary")
        if not base_salary:
            continue

        value = base_salary.get("value", {})
        return {
            "currency": base_salary.get("currency"),
            "min": value.get("minValue"),
            "max": value.get("maxValue"),
            "unit_period": value.get("unitText"),  # 예: "YEAR"
            "unit_note": "min/max는 원(KRW)이 아니라 만원 단위 숫자로 추정됨 (사이트 표기 방식 그대로, 자동 환산 안 함)",
        }
    return None


def fetch_incruit_salary(external_url: str) -> dict:
    """
    인크루트 원본 채용공고 페이지(jobdb_info/jobpost.asp)에서 급여 정보를 추출.
    ※ robots.txt 확인 결과, jobpost.asp 경로는 크롤링 허용 확인됨.
       (같은 인크루트 도메인이라도 jobpostcontpartner.asp 같은 본문설명 iframe 경로는
        robots.txt로 차단되어 있으므로 접근하지 않음 — 급여만 목적으로 최소 범위만 접근)

    2단계 시도:
      1순위: <script type="application/ld+json">의 baseSalary (숫자로 공개된 경우만 존재)
      2순위: jc_list 안의 "급여조건" 항목 텍스트 (비공개/카테고리성 값 포함, 항상 존재)
    """
    if not external_url or "incruit.com" not in external_url:
        return {}
    try:
        response = requests.get(external_url, headers=DETAIL_HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "euc-kr"  # 인크루트는 EUC-KR 인코딩 사이트
        soup = BeautifulSoup(response.text, "html.parser")

        # 1순위: JSON-LD 구조화 데이터
        ld_salary = extract_ld_json_salary(soup)

        # 2순위: jc_list 텍스트 (항상 시도 — raw 텍스트는 기록해두는 게 검증에 유용)
        salary_text = None
        for li in soup.select("ul.jc_list li"):
            label_elem = li.select_one("div.tt em")
            value_elem = li.select_one("div.txt em")
            if not label_elem or not value_elem:
                continue
            label = label_elem.get_text(strip=True)
            if label in ("급여조건", "급여", "월급여", "연봉", "시급"):
                salary_text = clean_text(value_elem.get_text(strip=True))
                break

        return {
            "incruit_url": external_url,
            "incruit_salary_raw": salary_text,
            "incruit_salary_ld_json": ld_salary,  # 숫자로 공개된 경우만 값이 있고, 아니면 None
            "incruit_salary_parsed": (
                categorize_salary(salary_text) if salary_text else None
            ),
        }
    except Exception as e:
        print(f"    ⚠️ 인크루트 급여 조회 실패: {e}")
        return {}


def enrich_with_details(
    jobs: list[dict], delay_sec: float = 1.5, fetch_incruit_salary_flag: bool = True
) -> list[dict]:
    """
    목록에서 얻은 jobs 각각에 대해 상세페이지를 방문해 필드를 보강.
    link에서 infoTypeCd, infoTypeGroup을 파싱해 사용.
    fetch_incruit_salary_flag=True면, 출처가 "인크루트"인 공고에 한해
    원본 사이트로 한 단계 더 들어가 실제 급여를 가져옴 (robots.txt 허용 경로만 접근).
    """
    from urllib.parse import urlparse, parse_qs

    for i, job in enumerate(jobs, 1):
        print(f"🔎 상세페이지 {i}/{len(jobs)}: {job.get('wanted_auth_no')}")

        link = job.get("link", "")
        qs = parse_qs(urlparse(link).query)
        info_type_cd = qs.get("infoTypeCd", [""])[0]
        info_type_group = qs.get("infoTypeGroup", [""])[0]

        detail = fetch_detail(job["wanted_auth_no"], info_type_cd, info_type_group)
        job.update(detail)

        # 인크루트 출처 공고면, robots.txt로 허용된 jobpost.asp 경로에서 실제 급여 보강 시도
        # (fetch_detail이 이미 받아온 external_apply_url을 재사용 -> work24에 중복 요청 안 함)
        if (
            fetch_incruit_salary_flag
            and job.get("source") == "인크루트"
            and job.get("external_apply_url")
        ):
            time.sleep(delay_sec)  # 인크루트로 나가는 요청도 동일하게 딜레이
            incruit_data = fetch_incruit_salary(job["external_apply_url"])
            job.update(incruit_data)

        # 제목에서 스킬 키워드 추출 (상세페이지 성공 여부와 무관하게 항상 가능)
        job["skills_from_title"] = extract_skills_from_title(job.get("title", ""))

        time.sleep(delay_sec)

    return jobs


def run_crawler(max_pages: int = 5, delay_sec: float = 1.5, extra_params: dict = None):
    """
    페이지네이션 순회하며 데이터 수집
    delay_sec: 요청 사이 딜레이 (서버 부하 방지 + 봇 탐지 회피)
    extra_params: BASE_PARAMS를 덮어쓰고 싶은 값 (예: 다른 지역/직종으로 바꾸고 싶을 때)
    """
    all_jobs = []
    seen_ids = set()  # wantedAuthNo 기준 중복 제거용

    for page in range(1, max_pages + 1):
        print(f"📄 {page}/{max_pages} 페이지 수집 중...")
        params = {
            **BASE_PARAMS,
            **(extra_params or {}),
            "currentPageNo": str(page),
            "pageIndex": str(page),
        }

        soup = fetch_list_page(params)
        jobs = extract_jobs(soup)

        if not jobs:
            print(f"페이지 {page}에서 더 이상 데이터 없음. 종료.")
            break

        new_jobs = [j for j in jobs if j["wanted_auth_no"] not in seen_ids]
        for j in new_jobs:
            seen_ids.add(j["wanted_auth_no"])

        all_jobs.extend(new_jobs)
        print(f"  └─ {len(new_jobs)}건 수집 (누적 {len(all_jobs)}건)")

        time.sleep(delay_sec)  # 사람처럼 보이기: 요청 간 딜레이

    return all_jobs


def save_to_csv(jobs: list[dict], filename: str = None):
    if not jobs:
        print("저장할 데이터가 없습니다.")
        return
    filename = filename or f"work24_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    pd.DataFrame(jobs).to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"✅ {len(jobs)}건을 {filename}에 저장했습니다.")
    return filename


DATASET_NOTES = {
    "skills_from_title": (
        "전체 공고 중 제목에 스킬 키워드가 명시된 일부(약 24%, 100건 테스트 기준)를 "
        "기준으로 한 참고 지표입니다. 제목에 해당 키워드가 없으면 실제로 그 스킬을 "
        "요구하더라도 잡히지 않습니다."
    ),
    "incruit_salary_raw": (
        "인크루트에 기재된 연봉 기준입니다. 다른 출처(사람인, 잡코리아, 고용24 자체등록 등) "
        "공고는 연봉 정보가 대부분 비공개라 이 항목이 비어 있습니다."
    ),
}


def save_to_json(jobs: list[dict], filename: str = None):
    if not jobs:
        print("저장할 데이터가 없습니다.")
        return
    import json

    filename = (
        filename or f"work24_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output = {
        "notes": DATASET_NOTES,  # 대시보드에 이 항목들을 쓸 때 툴팁/각주로 함께 표시할 것
        "jobs": jobs,
    }
    with open(filename, "w", encoding="utf-8") as f:
        # ensure_ascii=False: 한글이 유니코드 이스케이프(\uXXXX)로 안 바뀌고 그대로 저장됨
        # indent=2: 사람이 읽기 좋게 들여쓰기 (용량 신경쓰이면 없애도 됨)
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ {len(jobs)}건을 {filename}에 저장했습니다.")
    return filename


if __name__ == "__main__":
    # 1단계: 서울 + IT 관련 직종, 1페이지(100건) 목록 수집
    jobs = run_crawler(max_pages=1, delay_sec=1.5)

    if jobs:
        print(f"\n목록 수집 완료: {len(jobs)}건")
        print("--- 상세페이지 크롤링 시작 (전체) ---")

        # 2단계: 상세페이지 방문해서 모집인원/조회수/급여/기업정보 등 보강
        jobs = enrich_with_details(jobs, delay_sec=1.5)

        print("\n--- 첫 번째 공고 샘플 (구조 확인용) ---")
        print(jobs[0])
        print("---------------------------------------\n")

    save_to_json(jobs)
    # save_to_csv(jobs)  # 엑셀 등에서 표로 보고 싶을 때는 이 줄 주석 해제
