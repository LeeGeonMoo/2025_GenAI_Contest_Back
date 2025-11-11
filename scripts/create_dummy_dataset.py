# -*- coding: utf-8 -*-
"""
Realistic dummy notice HTML generator for NotiSNU.
- Diverse categories & departments
- Multiple layout variants (list/detail/card)
- Rich metadata (deadline, tags, contact, attachments, images)
- JSON index for downstream LLM/ETL pipeline
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import json
import random
import string
import textwrap
import itertools

# -----------------------------
# Config
# -----------------------------
OUTPUT_DIR = Path("docs/dummy_notices")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 42
COUNT = 120  # 생성 개수 (원하면 100~300 사이로 조정)

BASE_URL = "https://dummy.snu.ac.kr"

# 카테고리 확장
CATEGORIES = [
    "장학", "학사", "채용", "진로", "연구", "국제", "행사", "복지",
    "시설", "IT", "안전", "공모전", "세미나", "교육", "봉사",
]

# 학부/기관 샘플 확장
DEPARTMENTS = [
    "공과대학", "자유전공학부", "컴퓨터공학부", "전기정보공학부", "기계공학부",
    "수리과학부", "통계학과", "경제학부", "경영대학", "행정대학원",
    "의과대학", "간호대학", "약학대학", "자연과학대학", "미술대학",
    "음악대학", "사범대학", "국제대학원", "데이터사이언스대학원",
    "학생지원센터", "국제협력본부", "정보화본부", "중앙도서관",
]

CONTACTS = [
    ("학생지원센터", "02-880-1234", "support@snu.ac.kr"),
    ("전공사무실",   "02-880-5678", "major@snu.ac.kr"),
    ("학사과",       "02-880-2468", "academic@snu.ac.kr"),
    ("대학원교학팀", "02-880-9087", "grad@snu.ac.kr"),
    ("국제협력본부", "02-880-4445", "oia@snu.ac.kr"),
    ("취업센터",     "02-880-7777", "career@snu.ac.kr"),
    ("정보화본부",   "02-880-5555", "it@snu.ac.kr"),
]

TAGS_POOL = [
    "대학생활", "장학금", "학부생", "대학원생", "교환학생", "인턴십", "연구참여",
    "마감임박", "오프라인", "온라인", "현장행사", "설명회", "해외", "교내", "공모전",
    "AI", "데이터", "보안", "개발", "디자인", "문서양식", "서류전형", "면접",
]

IMAGES = [
    "https://picsum.photos/seed/noti1/960/540",
    "https://picsum.photos/seed/noti2/960/540",
    "https://picsum.photos/seed/noti3/960/540",
    "https://picsum.photos/seed/noti4/960/540",
]

# 카테고리별 제목 키워드
TITLE_KW = {
    "장학": ["국가장학", "교내장학", "가계곤란", "학업우수"],
    "학사": ["수강정정", "휴복학", "성적정정", "졸업요건", "등록금"],
    "채용": ["연구원 모집", "튜터 채용", "학부 RA", "행정조교"],
    "진로": ["커리어 특강", "멘토링", "이력서 클리닉"],
    "연구": ["URP 참가자", "랩 미팅 안내", "세미나 시리즈"],
    "국제": ["교환학생", "해외연수", "단기프로그램"],
    "행사": ["설명회", "박람회", "오리엔테이션", "개최 안내"],
    "복지": ["심리상담", "기숙사", "식당", "장애학생지원"],
    "시설": ["공사 안내", "출입통제", "정전 점검"],
    "IT":   ["VPN 점검", "포털 점검", "메일 서비스", "보안 업데이트"],
    "안전": ["대피훈련", "실험실 안전", "코로나 지침"],
    "공모전": ["아이디어 공모", "포스터 공모", "논문 공모"],
    "세미나": ["초청강연", "콜로퀴움", "워크숍"],
    "교육": ["특강", "부트캠프", "온라인 교육"],
    "봉사": ["자원봉사자 모집", "멘토 봉사"],
}

# 레이아웃 3종: list-like, detail-page, card-grid
LAYOUTS = ("list", "detail", "card")


@dataclass
class Notice:
    idx: int
    category: str
    department: str
    title: str
    posted: str
    deadline: str | None
    status: str  # normal | updated | extended | canceled
    body_html: str
    tags: list[str]
    contact_org: str
    contact_tel: str
    contact_email: str
    audience: str  # "학부생,대학원생" 등
    grades: str    # "1,2,3,4"
    majors: str    # "전체" 또는 전공 문자열
    location: str | None
    links: list[dict]
    attachments: list[dict]
    image_url: str | None
    source_url: str
    layout: str


# -----------------------------
# Utilities
# -----------------------------
def _rand_date_pair(idx: int) -> tuple[datetime, datetime | None]:
    # 게시일: 최근 120일 내
    posted = datetime.now() - timedelta(days=random.randint(1, 120), hours=random.randint(0, 23))
    # 65%는 마감 존재, 35%는 상시/공지
    if random.random() < 0.65:
        dl = posted + timedelta(days=random.randint(3, 30), hours=random.randint(0, 20))
        return posted, dl
    return posted, None


def _rand_status() -> str:
    r = random.random()
    if r < 0.08:
        return "canceled"
    if r < 0.18:
        return "extended"
    if r < 0.30:
        return "updated"
    return "normal"


def _rand_audience() -> str:
    pools = [
        "학부생", "대학원생", "전체 구성원", "신입생", "휴학생", "졸업예정자", "교원/직원"
    ]
    k = random.randint(1, 2)
    return ",".join(sorted(random.sample(pools, k)))


def _rand_grades() -> str:
    picks = sorted(random.sample([1, 2, 3, 4], random.randint(1, 4)))
    return ",".join(map(str, picks))


def _rand_majors() -> str:
    return "전체" if random.random() < 0.6 else random.choice(DEPARTMENTS)


def _rand_location() -> str | None:
    if random.random() < 0.6:
        halls = ["301동", "302동", "38동", "관정도서관", "종합체육관", "글로벌공학교육센터"]
        rooms = [f"{random.randint(101, 709)}호"]
        return f"{random.choice(halls)} {random.choice(rooms)}"
    return None


def _rand_attachments() -> list[dict]:
    exts = ["pdf", "hwp", "docx", "xlsx"]
    files = []
    for _ in range(random.randint(0, 3)):
        name = "첨부_" + "".join(random.choices(string.ascii_lowercase, k=6))
        ext = random.choice(exts)
        files.append({
            "name": f"{name}.{ext}",
            "url": f"{BASE_URL}/files/{name}.{ext}",
            "size": f"{random.randint(80, 2048)}KB",
        })
    return files


def _rand_links() -> list[dict]:
    links = []
    if random.random() < 0.7:
        links.append({"label": "신청 폼", "url": f"{BASE_URL}/apply/{random.randint(1000,9999)}"})
    if random.random() < 0.4:
        links.append({"label": "상세 안내", "url": f"{BASE_URL}/info/{random.randint(1000,9999)}"})
    return links


def _datefmt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    # 포맷 다양화: 60% 'YYYY-MM-DD', 40% 'YYYY.MM.DD HH:MM'
    if random.random() < 0.6:
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y.%m.%d %H:%M")


def _pick_title(category: str, department: str, idx: int) -> str:
    head = random.choice(TITLE_KW.get(category, ["안내"]))
    suffix = random.choice(["공지", "안내", "모집", "신청", "변경", "연장"])
    return f"[{department}] {head} {suffix} {idx:03d}"


def _section(title: str, content: str) -> str:
    return f"<section class='section'><h3>{title}</h3><p>{content}</p></section>"


def _bullet(title: str, items: list[str]) -> str:
    lis = "".join(f"<li>{i}</li>" for i in items)
    return f"<section class='section'><h3>{title}</h3><ul>{lis}</ul></section>"


def _table_schedule(rows: list[tuple[str, str]]) -> str:
    trs = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
    return f"""
    <section class='section'>
      <h3>일정</h3>
      <table class='schedule'><thead><tr><th>구분</th><th>일시</th></tr></thead>
      <tbody>{trs}</tbody></table>
    </section>
    """.strip()


def _compose_body(category: str, department: str, posted: datetime, deadline: datetime | None) -> str:
    # 공통 문장 Pool
    intro = random.choice([
        f"{department}에서 {category} 관련 안내드립니다.",
        f"{department} 주최 {category} 관련 주요 공지입니다.",
        f"{department}에서 다음과 같이 {category}를 진행합니다.",
    ])
    note = random.choice([
        "세부 내용 및 제출 양식은 첨부 파일을 확인하시기 바랍니다.",
        "지원 자격과 평가 기준을 반드시 확인하세요.",
        "마감 임박 시 트래픽 증가로 접속이 지연될 수 있습니다.",
        "문의가 많은 관계로 메일 답변이 지연될 수 있습니다.",
    ])
    # 카테고리 특화 섹션
    if category == "장학":
        requirements = _bullet("지원자격", [
            "직전학기 평점 3.5 이상(4.3 만점 기준)",
            "등록금 납부 및 재학 상태 유지",
            "타 장학금과 중복 수혜 시 제한 가능",
        ])
        benefits = _bullet("지원내용", [
            "등록금 일부 또는 전액",
            "생활비/기숙사비 일부",
            "우수자 소정의 장려금",
        ])
        docs = _bullet("제출서류", [
            "장학금 신청서(소정양식)",
            "성적증명서",
            "개인정보동의서",
        ])
        schedule = _table_schedule([
            ("서류 접수", posted.strftime("%Y-%m-%d")),
            ("결과 발표", (posted + timedelta(days=20)).strftime("%Y-%m-%d")),
        ])
        outro = _section("유의사항", note)
        return "\n".join([_section("개요", intro), requirements, benefits, docs, schedule, outro])

    if category in ("채용", "진로", "봉사"):
        req = _bullet("자격요건", [
            "학부 1~4학년 또는 대학원 재학",
            "기본 OA 활용 능력",
            "주 1회 회의 참석 가능자",
        ])
        work = _bullet("활동내용", [
            "현장 지원 및 자료 정리",
            "참가자 안내 및 질의응대",
            "성과 보고서 작성 보조",
        ])
        benefit = _bullet("혜택", [
            "활동비 지급", "경력증명서 발급", "우수자 시상"
        ])
        return "\n".join([_section("개요", intro), req, work, benefit, _section("기타", note)])

    if category in ("연구", "세미나"):
        agenda = _bullet("주요 주제", [
            "최신 연구 동향 소개",
            "발표 및 Q&A",
            "협업 과제 논의",
        ])
        schedule = _table_schedule([
            ("등록", posted.strftime("%Y.%m.%d %H:%M")),
            ("세미나", (posted + timedelta(days=7)).strftime("%Y.%m.%d %H:%M")),
        ])
        speaker = _bullet("연사", [
            "홍길동 교수(컴퓨터공학부)", "김연구 박사(데이터사이언스)"
        ])
        return "\n".join([_section("개요", intro), agenda, schedule, speaker, _section("참고", note)])

    if category in ("국제", "행사", "공모전", "교육"):
        info = _bullet("프로그램 안내", [
            "온/오프라인 병행 운영",
            "선착순 또는 서류 평가",
            "참가 인증서 발급(해당시)",
        ])
        howto = _bullet("신청방법", [
            "온라인 신청 폼 제출",
            "필요 시 면접 진행",
            "최종 합격자 개별 안내",
        ])
        award = _bullet("혜택/시상", [
            "참가비 지원(해당시)", "우수 팀/개인 시상", "전문가 멘토링"
        ])
        return "\n".join([_section("개요", intro), info, howto, award, _section("유의사항", note)])

    if category in ("시설", "IT", "안전", "복지", "학사"):
        details = _bullet("주요 내용", [
            "해당 기간 시설 점검 및 출입 제한",
            "시스템 보안 업데이트 및 서비스 재시작",
            "학사 일정(수강/휴복학/졸업) 안내",
        ])
        window = _table_schedule([
            ("작업 시작", posted.strftime("%Y-%m-%d %H:%M")),
            ("작업 종료", (posted + timedelta(hours=random.randint(2, 12))).strftime("%Y-%m-%d %H:%M")),
        ])
        faq = _bullet("FAQ", [
            "점검 중 서비스 이용이 불가할 수 있습니다.",
            "작업 상황에 따라 종료 시각이 변동될 수 있습니다.",
        ])
        return "\n".join([_section("개요", intro), details, window, faq, _section("문의", note)])

    # fallback
    return "\n".join([_section("개요", intro), _section("참고", note)])


def _render_layout(notice: Notice) -> str:
    # 공통 태그
    tags_html = "".join(f"<li>{t}</li>" for t in notice.tags)
    attachments_html = "".join(
        f"<li><a href='{a['url']}' download>{a['name']}</a> <span class='size'>{a['size']}</span></li>"
        for a in notice.attachments
    )
    links_html = "".join(f"<a class='btn' href='{l['url']}'>{l['label']}</a>" for l in notice.links)
    img_html = f"<img class='hero' src='{notice.image_url}' alt='notice image'/>" if notice.image_url else ""

    deadline_html = f"<span class='deadline'>{notice.deadline}</span>" if notice.deadline else "<span class='deadline none'>상시</span>"
    location_html = f"<span class='location'>{notice.location}</span>" if notice.location else ""

    status_badge = {
        "normal": "",
        "updated": "<span class='badge updated'>[수정]</span>",
        "extended": "<span class='badge extended'>[연장]</span>",
        "canceled": "<span class='badge canceled'>[취소]</span>",
    }[notice.status]

    base_attrs = (
        f"data-department='{notice.department}' "
        f"data-category='{notice.category}' "
        f"data-audience='{notice.audience}' "
        f"data-grades='{notice.grades}' "
        f"data-majors='{notice.majors}' "
    )

    # 레이아웃별 템플릿
    if notice.layout == "list":
        return f"""
<article class="notice notice--list" {base_attrs}>
  <h2 class="title"><a href="{notice.source_url}">{status_badge}{notice.title}</a></h2>
  <div class="meta">
    <span class="posted">{notice.posted}</span>
    {deadline_html}
    {location_html}
  </div>
  <div class="body">
    {img_html}
    {notice.body_html}
  </div>
  <ul class="tags">{tags_html}</ul>
  <div class="resources">
    <ul class="attachments">{attachments_html}</ul>
    <div class="links">{links_html}</div>
  </div>
  <footer class="contact">
    <span class="org">{notice.contact_org}</span>
    <span class="tel">{notice.contact_tel}</span>
    <a class="email" href="mailto:{notice.contact_email}">{notice.contact_email}</a>
  </footer>
</article>
""".strip()

    if notice.layout == "detail":
        return f"""
<main class="notice notice--detail" {base_attrs}>
  <header>
    <h1>{status_badge}{notice.title}</h1>
    <div class="meta">
      <span class="posted">{notice.posted}</span>
      {deadline_html}
      {location_html}
      <span class="dept">{notice.department}</span>
      <span class="cat">{notice.category}</span>
    </div>
  </header>
  {img_html}
  <article class="content">
    {notice.body_html}
  </article>
  <aside class="sidebar">
    <h3>태그</h3>
    <ul class="tags">{tags_html}</ul>
    <h3>첨부</h3>
    <ul class="attachments">{attachments_html}</ul>
    <div class="links">{links_html}</div>
    <div class="contact">
      <strong>문의</strong>
      <p>{notice.contact_org} / {notice.contact_tel}<br/>
         <a href="mailto:{notice.contact_email}">{notice.contact_email}</a></p>
    </div>
  </aside>
</main>
""".strip()

    # card
    return f"""
<div class="notice notice--card" {base_attrs}>
  <a class="cover" href="{notice.source_url}">
    {img_html}
  </a>
  <div class="content">
    <h3 class="title">{status_badge}{notice.title}</h3>
    <div class="meta">
      <span class="posted">{notice.posted}</span>
      {deadline_html}
    </div>
    <div class="excerpt">{notice.body_html[:300]}...</div>
    <ul class="tags">{tags_html}</ul>
  </div>
  <div class="footer">
    <ul class="attachments">{attachments_html}</ul>
    <div class="links">{links_html}</div>
  </div>
</div>
""".strip()


def _make_notice(idx: int) -> Notice:
    category = CATEGORIES[idx % len(CATEGORIES)]
    department = random.choice(DEPARTMENTS)
    posted_dt, deadline_dt = _rand_date_pair(idx)

    title = _pick_title(category, department, idx)
    status = _rand_status()
    body_html = _compose_body(category, department, posted_dt, deadline_dt)

    contact_org, tel, email = random.choice(CONTACTS)
    sampled_tags = set(random.sample(TAGS_POOL, random.randint(3, 6)))
    sampled_tags.add(category)
    tags = sorted(sampled_tags)
    audience = _rand_audience()
    grades = _rand_grades()
    majors = _rand_majors()
    location = _rand_location()
    links = _rand_links()
    attachments = _rand_attachments()
    image_url = random.choice(IMAGES) if random.random() < 0.55 else None
    layout = random.choice(LAYOUTS)

    return Notice(
        idx=idx,
        category=category,
        department=department,
        title=title,
        posted=_datefmt(posted_dt),
        deadline=_datefmt(deadline_dt),
        status=status,
        body_html=body_html,
        tags=tags,
        contact_org=contact_org,
        contact_tel=tel,
        contact_email=email,
        audience=audience,
        grades=grades,
        majors=majors,
        location=location,
        links=links,
        attachments=attachments,
        image_url=image_url,
        source_url=f"{BASE_URL}/notice/{idx:03d}",
        layout=layout,
    )


def _wrap_html(doc: str) -> str:
    # 간단한 스타일 포함 (파서 학습용 클래스/속성 보존)
    css = """
    <style>
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;line-height:1.6;margin:24px;color:#0b0f13}
    .notice{border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:18px 0;box-shadow:0 6px 18px rgba(0,0,0,.06)}
    .notice--card{display:grid;grid-template-columns:1fr 2fr;gap:12px}
    .notice .meta{display:flex;gap:10px;flex-wrap:wrap;color:#475569;font-size:0.92rem}
    .notice .tags{list-style:none;padding:0;margin:8px 0;display:flex;flex-wrap:wrap;gap:6px}
    .notice .tags li{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;padding:2px 8px}
    .notice .attachments{list-style:disc;margin-left:18px}
    .hero{width:100%;height:auto;border-radius:8px;margin:8px 0}
    .section{margin:10px 0}
    table.schedule{width:100%;border-collapse:collapse}
    table.schedule td, table.schedule th{border:1px solid #e5e7eb;padding:6px}
    .badge{margin-right:6px;padding:2px 6px;border-radius:6px;border:1px solid}
    .badge.updated{color:#7c3aed;border-color:#7c3aed}
    .badge.extended{color:#2563eb;border-color:#2563eb}
    .badge.canceled{color:#ef4444;border-color:#ef4444}
    .deadline.none{color:#94a3b8}
    .btn{display:inline-block;margin-right:8px;border:1px solid #cbd5e1;padding:4px 10px;border-radius:8px;text-decoration:none}
    </style>
    """
    return f"<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'><title>dummy notice</title>{css}</head><body>{doc}</body></html>"


def main():
    random.seed(RANDOM_SEED)
    index = []

    for idx in range(1, COUNT + 1):
        n = _make_notice(idx)
        html_core = _render_layout(n)
        html = _wrap_html(html_core)
        path = OUTPUT_DIR / f"notice_{idx:03d}.html"
        path.write_text(html, encoding="utf-8")

        meta = asdict(n)
        # 본문은 JSON에는 넣되, 너무 길면 요약 본문도 같이
        meta["excerpt"] = " ".join(n.body_html.split())[:180]
        index.append(meta)

    # 인덱스 저장 (파이프라인용)
    with open(OUTPUT_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(index)} dummy notices in {OUTPUT_DIR.resolve()}")
    print("Sample:", (OUTPUT_DIR / "notice_001.html").as_posix())

if __name__ == "__main__":
    main()
